#!/usr/bin/env python3
"""
install.py – Installations-Script für ESP32 Bodenfeuchte-Monitor
Läuft auf dem PC (Python 3) und überträgt alle Dateien auf den ESP32.
"""

import subprocess
import sys
import os

# ─────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ─────────────────────────────────────────────
def run(cmd, check=True):
    print("  $", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        raise RuntimeError("Befehl fehlgeschlagen: " + " ".join(cmd))
    return result

def ensure_mpremote():
    try:
        import mpremote
        print("✓ mpremote bereits installiert")
    except ImportError:
        print("→ Installiere mpremote ...")
        run([sys.executable, "-m", "pip", "install", "mpremote"])

COM_PORT = "COM7"  # wird in main() gesetzt

def mp(args, check=True):
    """Führt einen mpremote-Befehl aus."""
    return run([sys.executable, "-m", "mpremote", "connect", COM_PORT] + args, check=check)

# ─────────────────────────────────────────────
#  KONFIGURATION ABFRAGEN
# ─────────────────────────────────────────────
def ask(prompt, default=""):
    val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default

def collect_config():
    print("\n" + "═" * 50)
    print("  ESP32 Bodenfeuchte-Monitor – Setup")
    print("═" * 50)

    print("\n── WLAN ──────────────────────────────────")
    ssid     = ask("WLAN-Name (SSID)")
    password = ask("WLAN-Passwort")

    print("\n── MQTT (Home Assistant) ─────────────────")
    broker   = ask("MQTT Broker IP", "192.168.178.183")
    port     = ask("MQTT Port", "1883")
    user     = ask("MQTT Benutzername", "mqtt_esp32")
    pw_mqtt  = ask("MQTT Passwort", "sicheres_passwort_123")

    print("\n── Telegram ──────────────────────────────")
    token    = ask("Telegram Bot Token")
    chat_id  = ask("Telegram Chat-ID")

    print("\n── Zeitzone ──────────────────────────────")
    utc      = ask("UTC-Offset (Winter=1, Sommer=2)", "2")

    print("\n── Tagesupdate ───────────────────────────")
    mhour    = ask("Stunde Morgen-Update (0-23)", "8")
    mmin     = ask("Minute Morgen-Update (0-59)", "0")

    print("\n── Kalibrierung (ESP32 ADC 12-bit: 0-4095) ─")
    print("  Tipp: Sensor trocken in Luft → ca. 3500")
    print("        Sensor in Wasser       → ca. 1000")
    raw_dry  = ask("RAW_DRY (Trocken-Rohwert)", "3500")
    raw_wet  = ask("RAW_WET  (Nass-Rohwert)",   "1000")

    print("\n── Alarm ─────────────────────────────────")
    alarm_lo = ask("Alarm unter x % (trocken)", "30")
    alarm_hi = ask("Alarm über x % (Staunässe)", "90")

    return dict(
        ssid=ssid, password=password,
        broker=broker, port=port, user=user, pw_mqtt=pw_mqtt,
        token=token, chat_id=chat_id,
        utc=utc, mhour=mhour, mmin=mmin,
        raw_dry=raw_dry, raw_wet=raw_wet,
        alarm_lo=alarm_lo, alarm_hi=alarm_hi
    )

def write_config(cfg):
    content = f"""# config.py – generiert von install.py (ESP32 NodeMCU)

# WLAN
WIFI_SSID     = "{cfg['ssid']}"
WIFI_PASSWORD = "{cfg['password']}"

# MQTT
MQTT_BROKER    = "{cfg['broker']}"
MQTT_PORT      = {cfg['port']}
MQTT_CLIENT_ID = "esp32_soil_sensor"
MQTT_TOPIC     = b"home/garden/soil_moisture"
MQTT_CMD_TOPIC = b"home/garden/soil_moisture/cmd"
MQTT_CAL_TOPIC = b"home/garden/soil_moisture/calibration"
MQTT_USER      = "{cfg['user']}"
MQTT_PASSWORD  = "{cfg['pw_mqtt']}"

# Telegram
TELEGRAM_TOKEN   = "{cfg['token']}"
TELEGRAM_CHAT_ID = {cfg['chat_id']}

# Zeitzone (Deutschland: Winter=1, Sommer=2)
UTC_OFFSET = {cfg['utc']}

# Tagesupdate
MORNING_HOUR   = {cfg['mhour']}
MORNING_MINUTE = {cfg['mmin']}

# Sensor-Startwerte (ESP32 ADC 12-bit: 0–4095)
RAW_DRY = {cfg['raw_dry']}
RAW_WET  = {cfg['raw_wet']}

# Alarm
ALARM_THRESHOLD = {cfg['alarm_lo']}
ALARM_WET       = {cfg['alarm_hi']}
ALARM_COOLDOWN  = 3600

# Intervalle
PUBLISH_INTERVAL = 600
COMMAND_INTERVAL = 10
SAMPLES          = 10
"""
    with open("config.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ config.py geschrieben")

# ─────────────────────────────────────────────
#  DATEIEN ÜBERTRAGEN
# ─────────────────────────────────────────────
def upload_files():
    files = ["config.py", "main.py", "ota_updater.py", "version.json"]
    print("\n── Dateien übertragen ────────────────────")
    for f in files:
        if not os.path.exists(f):
            print(f"  ⚠ {f} nicht gefunden, übersprungen")
            continue
        mp(["fs", "cp", f, ":" + f])
        print(f"  ✓ {f} übertragen")

def install_umqtt(ssid, password):
    print("\n── umqtt.simple installieren ─────────────")
    print("  → ESP32 verbindet sich mit WLAN für Download ...")
    script = (
        "import network, time\n"
        "w = network.WLAN(network.STA_IF)\n"
        "w.active(True)\n"
        f"w.connect(\"{ssid}\", \"{password}\")\n"
        "t = 20\n"
        "while not w.isconnected() and t > 0:\n"
        "    time.sleep(1)\n"
        "    t -= 1\n"
        "if not w.isconnected():\n"
        "    raise RuntimeError('WLAN fehlgeschlagen')\n"
        "print('WLAN:', w.ifconfig()[0])\n"
        "import mip\n"
        "mip.install('umqtt.simple')\n"
        "print('umqtt.simple installiert')"
    )
    mp(["exec", script])
    print("  ✓ umqtt.simple installiert")

def reboot():
    print("\n── ESP32 neu starten ─────────────────────")
    mp(["exec", "import machine; machine.reset()"], check=False)
    print("  ✓ Neustart ausgelöst")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    global COM_PORT
    print("\n🌱 ESP32 Bodenfeuchte-Monitor – Installer")
    print("─" * 50)
    print("Voraussetzungen:")
    print("  • Python 3 auf dem PC")
    print("  • MicroPython auf dem ESP32 geflasht")
    print("  • ESP32 per USB verbunden")
    print("─" * 50)

    ensure_mpremote()

    COM_PORT = ask("COM-Port des ESP32", "COM7")

    print("\n→ Suche ESP32 auf", COM_PORT, "...")
    mp(["exec", "import sys; print(sys.implementation)"])

    cfg = collect_config()
    write_config(cfg)
    install_umqtt(cfg['ssid'], cfg['password'])
    upload_files()
    reboot()

    print("\n" + "═" * 50)
    print("  ✅ Installation abgeschlossen!")
    print("  📡 Warte ~10 Sekunden, dann Browser öffnen:")
    print("  → WLAN-Router-Übersicht: ESP32-IP suchen")
    print("  → http://<ESP32-IP>")
    print()
    print("  ⚠️  OTA Setup:")
    print("  → ota_updater.py: GITHUB_USER anpassen!")
    print("  → version.json auf GitHub committen")
    print("═" * 50 + "\n")

if __name__ == "__main__":
    main()
