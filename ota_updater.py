# ota_updater.py – OTA Script-Update für ESP32 Bodenfeuchte-Monitor
# Lädt main.py direkt von GitHub und startet den ESP32 neu.
#
# Aufruf:
#   import ota_updater
#   ota_updater.check_and_update()
#
# Oder per Telegram: /ota_update (in main.py integriert)
# Oder per MQTT:    Befehl "ota_update" auf home/garden/soil_moisture/cmd

import urequests
import ujson
import machine
import gc

# ─────────────────────────────────────────────
#  KONFIGURATION
#  GitHub Raw URLs deiner Dateien:
#  https://raw.githubusercontent.com/<user>/<repo>/<branch>/<datei>
# ─────────────────────────────────────────────
GITHUB_USER   = "DEIN_GITHUB_USERNAME"
GITHUB_REPO   = "ESP32-Bodenfeuchtigkeit-HA"
GITHUB_BRANCH = "main"

# Dateien die per OTA aktualisiert werden (config.py wird NICHT überschrieben!)
OTA_FILES = ["main.py", "ota_updater.py"]

# Versions-URL: JSON mit {"version": "1.2.3"} auf GitHub
VERSION_URL = (
    "https://raw.githubusercontent.com/"
    + GITHUB_USER + "/" + GITHUB_REPO + "/" + GITHUB_BRANCH
    + "/version.json"
)

# Lokale Version (wird mit GitHub verglichen)
LOCAL_VERSION_FILE = "version.json"
LOCAL_VERSION      = "1.0.0"

def _raw_url(filename):
    return (
        "https://raw.githubusercontent.com/"
        + GITHUB_USER + "/" + GITHUB_REPO + "/" + GITHUB_BRANCH
        + "/" + filename
    )

def _read_local_version():
    try:
        with open(LOCAL_VERSION_FILE, "r") as f:
            return ujson.load(f).get("version", LOCAL_VERSION)
    except:
        return LOCAL_VERSION

def _fetch_remote_version():
    gc.collect()
    try:
        r    = urequests.get(VERSION_URL, timeout=10)
        data = ujson.loads(r.text)
        r.close()
        gc.collect()
        return data.get("version", "0.0.0")
    except Exception as e:
        print("OTA Version-Check Fehler:", e)
        gc.collect()
        return None

def _download_file(filename):
    """Lädt eine Datei von GitHub und speichert sie als <filename>.new"""
    url  = _raw_url(filename)
    dest = filename + ".new"
    print("OTA Download:", url)
    gc.collect()
    try:
        r = urequests.get(url, timeout=30)
        if r.status_code != 200:
            print("OTA HTTP Fehler:", r.status_code)
            r.close()
            gc.collect()
            return False
        with open(dest, "w") as f:
            f.write(r.text)
        r.close()
        gc.collect()
        print("OTA gespeichert:", dest)
        return True
    except Exception as e:
        print("OTA Download Fehler:", e)
        gc.collect()
        return False

def _apply_updates(files):
    """Benennt .new Dateien in finale Namen um (atomarer Schritt)."""
    import uos
    for filename in files:
        src = filename + ".new"
        try:
            uos.rename(src, filename)
            print("OTA angewendet:", filename)
        except Exception as e:
            print("OTA rename Fehler:", filename, e)
            return False
    return True

def _save_version(version):
    try:
        with open(LOCAL_VERSION_FILE, "w") as f:
            ujson.dump({"version": version}, f)
    except Exception as e:
        print("OTA Version speichern Fehler:", e)

def check_and_update(force=False, notify_fn=None):
    """
    Prüft auf neue Version und führt Update durch.

    Args:
        force:     Update erzwingen, auch wenn Version gleich
        notify_fn: Funktion(str) zum Senden von Statusmeldungen (z.B. send_telegram)

    Returns:
        True wenn Update durchgeführt, False sonst
    """
    def _log(msg):
        print(msg)
        if notify_fn:
            try:
                notify_fn(msg)
            except:
                pass

    local_ver  = _read_local_version()
    _log("OTA: Lokale Version: " + local_ver)

    remote_ver = _fetch_remote_version()
    if remote_ver is None:
        _log("OTA: GitHub nicht erreichbar.")
        return False

    _log("OTA: GitHub Version: " + remote_ver)

    if not force and remote_ver == local_ver:
        _log("OTA: Kein Update nötig – Version aktuell.")
        return False

    _log("OTA: Update verfügbar! " + local_ver + " → " + remote_ver + "\nLade Dateien ...")

    # Alle Dateien herunterladen
    downloaded = []
    for filename in OTA_FILES:
        if _download_file(filename):
            downloaded.append(filename)
        else:
            _log("OTA: FEHLER beim Download von " + filename + " – Abbruch.")
            # Temporäre Dateien aufräumen
            import uos
            for f in downloaded:
                try:
                    uos.remove(f + ".new")
                except:
                    pass
            return False

    # Updates anwenden
    if not _apply_updates(downloaded):
        _log("OTA: FEHLER beim Anwenden – Abbruch.")
        return False

    # Neue Version speichern
    _save_version(remote_ver)
    _log("OTA: ✅ Update auf " + remote_ver + " erfolgreich!\nNeustart in 3 Sekunden ...")

    import time
    time.sleep(3)
    machine.reset()
    return True

def get_version():
    """Gibt die aktuell installierte Version zurück."""
    return _read_local_version()
