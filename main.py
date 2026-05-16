# main.py – Bodenfeuchte-Monitor
# ESP32 NodeMCU | Webserver + MQTT + Telegram + Kalibrierung + OTA
import network
import socket
import time
import ntptime
import machine
import ujson
import urequests
import gc
from umqtt.simple import MQTTClient
import ota_updater
from config import (
    WIFI_SSID, WIFI_PASSWORD,
    MQTT_BROKER, MQTT_PORT, MQTT_CLIENT_ID,
    MQTT_TOPIC, MQTT_CMD_TOPIC, MQTT_CAL_TOPIC,
    MQTT_USER, MQTT_PASSWORD,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    UTC_OFFSET, MORNING_HOUR, MORNING_MINUTE,
    ALARM_THRESHOLD, ALARM_WET, ALARM_COOLDOWN,
    PUBLISH_INTERVAL, COMMAND_INTERVAL, SAMPLES
)
import config as cfg

# ─────────────────────────────────────────────
#  KALIBRIERUNG – laden/speichern
# ─────────────────────────────────────────────
RAW_DRY = cfg.RAW_DRY
RAW_WET  = cfg.RAW_WET
CAL_FILE = "calibration.json"

def load_calibration():
    global RAW_DRY, RAW_WET
    try:
        with open(CAL_FILE, "r") as f:
            data = ujson.load(f)
            RAW_DRY = data.get("raw_dry", cfg.RAW_DRY)
            RAW_WET  = data.get("raw_wet",  cfg.RAW_WET)
            print("Kalibrierung geladen: DRY={} WET={}".format(RAW_DRY, RAW_WET))
    except:
        print("Keine calibration.json – nutze config.py Werte")

def save_calibration():
    try:
        with open(CAL_FILE, "w") as f:
            ujson.dump({"raw_dry": RAW_DRY, "raw_wet": RAW_WET}, f)
        print("Kalibrierung gespeichert: DRY={} WET={}".format(RAW_DRY, RAW_WET))
    except Exception as e:
        print("Speicherfehler:", e)

# ─────────────────────────────────────────────
#  HARDWARE – ESP32
#  ADC-Pin: GPIO36 (VP/SVP) = ADC1_CH0
#  Wichtig: ADC2 ist bei aktivem WiFi NICHT nutzbar!
#  Attenuation ATTN_11DB → Messbereich 0–3,9V (effektiv 0–3,3V bei 3V3-Versorgung)
# ─────────────────────────────────────────────
adc = machine.ADC(machine.Pin(36))
adc.atten(machine.ADC.ATTN_11DB)      # Messbereich bis ~3,9V
adc.width(machine.ADC.WIDTH_12BIT)    # 12-bit → Wertebereich 0–4095

# Onboard-LED: GPIO2 (auf den meisten ESP32 NodeMCU Boards)
onboard_led = machine.Pin(2, machine.Pin.OUT)

def read_raw():
    """Liest SAMPLES Messungen und gibt den Mittelwert zurück (0–4095)."""
    total = 0
    for _ in range(SAMPLES):
        total += adc.read()
        time.sleep_ms(10)
    return total // SAMPLES

def raw_to_percent(raw):
    """
    Kapazitiver Sensor: hoher ADC-Wert = trocken, niedriger ADC-Wert = nass.
    RAW_DRY > RAW_WET
    """
    pct = (RAW_DRY - raw) / (RAW_DRY - RAW_WET) * 100
    return max(0.0, min(100.0, round(pct, 1)))

def read_moisture():
    raw = read_raw()
    return raw_to_percent(raw), raw

def calibrate_dry():
    global RAW_DRY
    RAW_DRY = read_raw()
    save_calibration()
    publish_calibration()
    msg = "Trocken-Kalibrierung gesetzt: RAW_DRY={}".format(RAW_DRY)
    print(msg)
    send_telegram("Kalibrierung gespeichert\n" + msg)

def calibrate_wet():
    global RAW_WET
    RAW_WET = read_raw()
    save_calibration()
    publish_calibration()
    msg = "Nass-Kalibrierung gesetzt: RAW_WET={}".format(RAW_WET)
    print(msg)
    send_telegram("Kalibrierung gespeichert\n" + msg)

# ─────────────────────────────────────────────
#  WLAN
# ─────────────────────────────────────────────
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Verbinde mit WLAN ...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            onboard_led.value(not onboard_led.value())
            time.sleep(0.5)
            timeout -= 1
        if not wlan.isconnected():
            raise RuntimeError("WLAN fehlgeschlagen!")
    onboard_led.on()
    print("WLAN verbunden:", wlan.ifconfig()[0])
    return wlan.ifconfig()[0]

# ─────────────────────────────────────────────
#  ZEIT
# ─────────────────────────────────────────────
def sync_time():
    try:
        ntptime.settime()
        print("Zeit synchronisiert")
    except Exception as e:
        print("NTP-Fehler:", e)

def local_time():
    return time.localtime(time.time() + UTC_OFFSET * 3600)

def time_str():
    t = local_time()
    return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])

def date_str():
    t = local_time()
    return "{:02d}.{:02d}.{}".format(t[2], t[1], t[0])

# ─────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(message):
    url     = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    payload = ujson.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message})
    gc.collect()
    try:
        r = urequests.post(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        print("Telegram:", r.status_code)
        r.close()
    except Exception as e:
        print("Telegram Fehler:", e)
    gc.collect()

last_update_id = 0

def init_telegram_offset():
    global last_update_id
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/getUpdates?limit=1&timeout=0"
    gc.collect()
    try:
        r    = urequests.get(url)
        body = r.text
        r.close()
        gc.collect()
        data    = ujson.loads(body)
        results = data.get("result", [])
        if results:
            last_update_id = results[-1]["update_id"]
            print("Telegram Offset:", last_update_id)
    except Exception as e:
        print("Telegram Offset Fehler:", e)
    gc.collect()

def check_telegram_commands(moisture, raw):
    global last_update_id
    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/getUpdates?offset="
        + str(last_update_id + 1)
        + "&limit=5&timeout=0"
    )
    gc.collect()
    try:
        r    = urequests.get(url)
        body = r.text
        r.close()
        gc.collect()

        data    = ujson.loads(body)
        updates = data.get("result", [])
        if updates:
            print("Updates:", len(updates))

        for update in updates:
            last_update_id = update["update_id"]
            msg     = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            text = msg.get("text", "").strip().lower()
            print("Befehl:", text)
            gc.collect()

            if text in ("/test", "/status"):
                _send_status(moisture, raw)
            elif text in ("/hilfe", "/help"):
                send_telegram(
                    "Verfuegbare Befehle:\n\n"
                    "/test      - Sensorwert abfragen\n"
                    "/status    - Gleich wie /test\n"
                    "/info      - Systeminformationen\n"
                    "/alarm     - Alarmschwelle\n"
                    "/cal_dry   - Trocken kalibrieren\n"
                    "/cal_wet   - Nass kalibrieren\n"
                    "/cal_info  - Kalibrierung anzeigen\n"
                    "/ota_update - Update von GitHub laden\n"
                    "/ota_force  - Update erzwingen\n"
                    "/hilfe      - Diese Hilfe"
                )
            elif text == "/info":
                uptime_h = time.time() // 3600
                send_telegram(
                    "Systeminformationen\n"
                    "Datum:     "  + date_str()            + "\n"
                    "Uhrzeit:   "  + time_str()            + "\n"
                    "Uptime:    "  + str(uptime_h)         + " h\n"
                    "MQTT:      "  + MQTT_BROKER           + "\n"
                    "Intervall: "  + str(PUBLISH_INTERVAL//60) + " min\n"
                    "Samples:   "  + str(SAMPLES)          + "\n"
                    "Board:     ESP32 NodeMCU\n"
                    "Version:   " + ota_updater.get_version()
                )
            elif text == "/alarm":
                send_telegram(
                    "Alarm-Einstellungen\n"
                    "Zu trocken: unter " + str(ALARM_THRESHOLD) + " %\n"
                    "Zu nass:    ueber  " + str(ALARM_WET)       + " %\n"
                    "Cooldown:   "        + str(ALARM_COOLDOWN // 60) + " Min"
                )
            elif text == "/cal_dry":
                send_telegram("Messe Trocken-Wert ...")
                calibrate_dry()
            elif text == "/cal_wet":
                send_telegram("Messe Nass-Wert ...")
                calibrate_wet()
            elif text == "/cal_info":
                pct_now = raw_to_percent(raw)
                send_telegram(
                    "Kalibrierung\n"
                    "RAW_DRY: "  + str(RAW_DRY) + " (0 %)\n"
                    "RAW_WET: "  + str(RAW_WET)  + " (100 %)\n"
                    "Aktuell: "  + str(raw)       + " raw\n"
                    "         "  + str(pct_now)   + " %"
                )
            elif text == "/ota_update":
                send_telegram("OTA: Prüfe auf Update von GitHub ...")
                ota_updater.check_and_update(notify_fn=send_telegram)
            elif text == "/ota_force":
                send_telegram("OTA: Erzwinge Update von GitHub ...")
                ota_updater.check_and_update(force=True, notify_fn=send_telegram)
            else:
                send_telegram("Unbekannt: " + text + "\nTippe /hilfe")
            gc.collect()

    except Exception as e:
        print("Telegram polling Fehler:", e)
        gc.collect()

def _send_status(moisture, raw):
    status = (
        "Feucht - alles gut!"          if moisture >= 50
        else "Trocken - bald giessen!" if moisture >= 25
        else "SEHR TROCKEN - jetzt giessen!"
    )
    send_telegram(
        "Sensor-Status\n"
        "Datum:   "  + date_str()    + "\n"
        "Uhrzeit: "  + time_str()    + "\n"
        "Feuchte: "  + str(moisture) + " %\n"
        "ADC:     "  + str(raw)      + "\n"
        "Status:  "  + status
    )

# ─────────────────────────────────────────────
#  TAGESUPDATE
# ─────────────────────────────────────────────
last_morning_day = -1

def check_morning_update(moisture, raw):
    global last_morning_day
    t   = local_time()
    day = t[2]
    if t[3] == MORNING_HOUR and t[4] == MORNING_MINUTE and day != last_morning_day:
        last_morning_day = day
        status = (
            "Feucht"       if moisture >= 50
            else "Trocken" if moisture >= 25
            else "SEHR TROCKEN"
        )
        send_telegram(
            "Guten Morgen! Tagesbericht\n"
            "Datum:   " + date_str()    + "\n"
            "Uhrzeit: " + time_str()    + "\n"
            "Feuchte: " + str(moisture) + " %\n"
            "ADC:     " + str(raw)      + "\n"
            "Status:  " + status
        )
        print("Tagesupdate gesendet")

# ─────────────────────────────────────────────
#  MQTT
# ─────────────────────────────────────────────
mqtt_client = None

def mqtt_callback(topic, msg):
    """Empfängt Kalibrierungs- und OTA-Befehle von Home Assistant."""
    cmd = msg.decode().strip()
    print("MQTT Befehl:", cmd)
    if cmd == "cal_dry":
        send_telegram("HA: Starte Trocken-Kalibrierung ...")
        calibrate_dry()
    elif cmd == "cal_wet":
        send_telegram("HA: Starte Nass-Kalibrierung ...")
        calibrate_wet()
    elif cmd == "ota_update":
        send_telegram("HA: Starte OTA Update ...")
        ota_updater.check_and_update(notify_fn=send_telegram)
    elif cmd == "ota_force":
        send_telegram("HA: Erzwinge OTA Update ...")
        ota_updater.check_and_update(force=True, notify_fn=send_telegram)

def connect_mqtt():
    global mqtt_client
    try:
        client = MQTTClient(
            MQTT_CLIENT_ID, MQTT_BROKER,
            port=MQTT_PORT,
            user=MQTT_USER,
            password=MQTT_PASSWORD,
            keepalive=120
        )
        client.set_callback(mqtt_callback)
        client.connect()
        client.subscribe(MQTT_CMD_TOPIC)
        mqtt_client = client
        print("MQTT verbunden, lausche auf:", MQTT_CMD_TOPIC)
        return True
    except Exception as e:
        print("MQTT-Fehler:", e)
        mqtt_client = None
        return False

def publish_mqtt(moisture, raw):
    global mqtt_client
    if mqtt_client is None:
        if not connect_mqtt():
            return
    payload = ujson.dumps({
        "moisture": moisture,
        "raw":      raw,
        "unit":     "%",
        "time":     time_str(),
        "date":     date_str()
    })
    try:
        mqtt_client.publish(MQTT_TOPIC, payload.encode(), retain=True)
        print("MQTT publish ->", payload)
    except Exception as e:
        print("MQTT publish Fehler:", e)
        mqtt_client = None

def publish_calibration():
    global mqtt_client
    if mqtt_client is None:
        return
    payload = ujson.dumps({"raw_dry": RAW_DRY, "raw_wet": RAW_WET})
    try:
        mqtt_client.publish(MQTT_CAL_TOPIC, payload.encode(), retain=True)
        print("Kalibrierung publiziert")
    except Exception as e:
        print("MQTT cal Fehler:", e)

def mqtt_check():
    global mqtt_client
    if mqtt_client is None:
        connect_mqtt()
        return
    try:
        mqtt_client.check_msg()
    except Exception as e:
        print("MQTT check Fehler:", e)
        mqtt_client = None

# ─────────────────────────────────────────────
#  WEBSERVER
# ─────────────────────────────────────────────
def build_html(moisture, raw):
    color = (
        "#4CAF50" if moisture >= 50
        else "#FF9800" if moisture >= 25
        else "#F44336"
    )
    status = (
        "Feucht"         if moisture >= 50
        else "Trocken"   if moisture >= 25
        else "Sehr trocken!"
    )
    emoji = "💧" if moisture >= 50 else "⚠️" if moisture >= 25 else "🔴"
    next_update = PUBLISH_INTERVAL // 60

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bodenfeuchte</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:sans-serif;background:#1a1a2e;color:#eee;
        display:flex;flex-direction:column;align-items:center;
        padding:1.5rem;min-height:100vh}}
  h1{{font-size:1.4rem;margin-bottom:1.2rem;color:#aaa}}
  .card{{background:#16213e;border-radius:16px;padding:1.8rem;
         width:100%;max-width:340px;text-align:center;
         box-shadow:0 4px 20px #0006;margin-bottom:1rem}}
  .card h2{{font-size:.85rem;color:#666;margin-bottom:1rem;
             text-transform:uppercase;letter-spacing:.05em}}
  .gauge{{font-size:3.5rem;font-weight:700;color:{color}}}
  .label{{font-size:.85rem;color:#aaa;margin-top:.4rem}}
  .bar-bg{{background:#0f3460;border-radius:8px;height:16px;
            margin:.9rem 0;overflow:hidden}}
  .bar{{height:100%;border-radius:8px;background:{color};width:{moisture}%}}
  .status{{font-size:.95rem;color:{color};margin-top:.5rem}}
  .meta{{font-size:.75rem;color:#555;margin-top:.8rem;line-height:1.6}}
  .cal-grid{{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;
              margin-top:.5rem}}
  .btn{{padding:.6rem;border:none;border-radius:8px;
        font-size:.85rem;cursor:pointer;font-weight:600;
        text-decoration:none;display:block;text-align:center}}
  .btn-dry{{background:#FF9800;color:#000}}
  .btn-wet{{background:#2196F3;color:#fff}}
  .cal-info{{display:grid;grid-template-columns:1fr 1fr;
              gap:.4rem;margin-top:.7rem;font-size:.8rem}}
  .cal-val{{background:#0f3460;border-radius:6px;padding:.4rem;text-align:center}}
  .cal-val span{{display:block;color:#aaa;font-size:.7rem}}
  .raw-big{{font-size:1.3rem;font-weight:700;color:#4fc3f7}}
  .chip{{display:inline-block;background:#0f3460;border-radius:20px;
         padding:.2rem .7rem;font-size:.7rem;color:#4fc3f7;margin-top:.5rem}}
  footer{{font-size:.7rem;color:#444;margin-top:1rem}}
</style>
</head>
<body>
<h1>🌱 Bodenfeuchte-Monitor</h1>

<div class="card">
  <h2>Aktueller Messwert</h2>
  <div class="gauge">{moisture}%</div>
  <div class="label">Bodenfeuchte</div>
  <div class="bar-bg"><div class="bar"></div></div>
  <div class="status">{emoji} {status}</div>
  <div class="meta">
    ADC-Rohwert: {raw} / 4095<br>
    {date_str()} {time_str()}<br>
    Naechstes Update: ~{next_update} Min
  </div>
  <span class="chip">ESP32 NodeMCU · GPIO36</span>
</div>

<div class="card">
  <h2>Kalibrierung</h2>
  <div class="cal-info">
    <div class="cal-val">
      <span>Trocken (0%)</span>
      <div class="raw-big">{RAW_DRY}</div>
    </div>
    <div class="cal-val">
      <span>Nass (100%)</span>
      <div class="raw-big">{RAW_WET}</div>
    </div>
    <div class="cal-val">
      <span>Aktuell RAW</span>
      <div class="raw-big">{raw}</div>
    </div>
    <div class="cal-val">
      <span>Aktuell %</span>
      <div class="raw-big">{moisture}%</div>
    </div>
  </div>
  <div class="cal-grid" style="margin-top:1rem">
    <a class="btn btn-dry" href="/cal/dry">
      🏜 Trocken setzen
    </a>
    <a class="btn btn-wet" href="/cal/wet">
      💧 Nass setzen
    </a>
  </div>
  <div class="meta" style="margin-top:.8rem">
    Sensor trocken in Luft halten → Trocken setzen<br>
    Sensor in Wasser tauchen → Nass setzen
  </div>
</div>

<footer>ESP32 NodeMCU (diymore) &nbsp;|&nbsp; MicroPython &nbsp;|&nbsp; ADC 12-bit</footer>
</body>
</html>"""

def build_cal_result_html(action, raw_val, label):
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="3;url=/">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalibrierung</title>
<style>
  body{{font-family:sans-serif;background:#1a1a2e;color:#eee;
        display:flex;flex-direction:column;align-items:center;
        justify-content:center;min-height:100vh;text-align:center;padding:2rem}}
  .card{{background:#16213e;border-radius:16px;padding:2rem;max-width:300px}}
  .big{{font-size:3rem;margin:.5rem 0}}
  .val{{font-size:1.5rem;font-weight:700;color:#4fc3f7;margin:.5rem 0}}
  p{{color:#aaa;font-size:.85rem;margin-top:1rem}}
</style>
</head>
<body>
<div class="card">
  <div class="big">✅</div>
  <div>{label} gesetzt</div>
  <div class="val">{raw_val}</div>
  <p>Weiterleitung in 3 Sekunden ...</p>
</div>
</body>
</html>"""

def serve_request(cl, moisture, raw):
    try:
        request = cl.recv(1024).decode()
        path    = request.split(" ")[1] if " " in request else "/"

        if path == "/data":
            body = ujson.dumps({
                "moisture": moisture,
                "raw":      raw,
                "raw_dry":  RAW_DRY,
                "raw_wet":  RAW_WET,
                "unit":     "%",
                "time":     time_str(),
                "date":     date_str()
            })
            cl.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n\r\n"
                + body.encode()
            )

        elif path == "/cal/dry":
            calibrate_dry()
            html = build_cal_result_html("dry", RAW_DRY, "Trocken-Wert")
            cl.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            cl.write(html.encode())

        elif path == "/cal/wet":
            calibrate_wet()
            html = build_cal_result_html("wet", RAW_WET, "Nass-Wert")
            cl.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            cl.write(html.encode())

        else:
            html = build_html(moisture, raw)
            cl.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            mv = memoryview(html.encode())
            for i in range(0, len(mv), 512):
                cl.write(mv[i:i+512])

    except Exception as e:
        print("Request-Fehler:", e)
    finally:
        cl.close()

# ─────────────────────────────────────────────
#  HAUPTSCHLEIFE
# ─────────────────────────────────────────────
def main():
    load_calibration()
    ip = connect_wifi()
    sync_time()
    connect_mqtt()
    init_telegram_offset()

    moisture, raw = read_moisture()
    publish_mqtt(moisture, raw)
    publish_calibration()

    send_telegram(
        "ESP32 gestartet\n"
        "Datum:     " + date_str()              + "\n"
        "Uhrzeit:   " + time_str()              + "\n"
        "IP:        " + ip                      + "\n"
        "Feuchte:   " + str(moisture)           + " %\n"
        "ADC-Raw:   " + str(raw)                + " / 4095\n"
        "Intervall: " + str(PUBLISH_INTERVAL//60) + " min\n"
        "Version:   " + ota_updater.get_version() + "\n"
        "Befehle:   /hilfe"
    )

    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    srv  = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(addr)
    srv.listen(2)
    srv.settimeout(1)
    print("Webserver: http://", ip)

    last_publish       = time.time()
    last_alarm         = 0
    last_command_check = 0

    while True:
        now = time.time()

        # ── MQTT Befehle prüfen (HA Kalibrierung) ─
        mqtt_check()

        # ── Sensor + MQTT alle 10 Minuten ─────────
        if now - last_publish >= PUBLISH_INTERVAL:
            moisture, raw = read_moisture()
            publish_mqtt(moisture, raw)
            last_publish = now

            # Alarme
            if moisture < ALARM_THRESHOLD:
                if now - last_alarm >= ALARM_COOLDOWN:
                    send_telegram(
                        "Pflanze braucht Wasser!\n"
                        "Feuchte: " + str(moisture) + " %\n"
                        "Uhrzeit: " + time_str()
                    )
                    last_alarm = now
            elif moisture > ALARM_WET:
                if now - last_alarm >= ALARM_COOLDOWN:
                    send_telegram(
                        "Achtung Staunaesse!\n"
                        "Feuchte: " + str(moisture) + " %\n"
                        "Uhrzeit: " + time_str()
                    )
                    last_alarm = now

            check_morning_update(moisture, raw)

        # ── Telegram Befehle alle 10 Sekunden ─────
        if now - last_command_check >= COMMAND_INTERVAL:
            check_telegram_commands(moisture, raw)
            last_command_check = now

        # ── HTTP-Anfragen ──────────────────────────
        try:
            cl, _ = srv.accept()
            cl.settimeout(5)
            serve_request(cl, moisture, raw)
        except OSError:
            pass

main()
