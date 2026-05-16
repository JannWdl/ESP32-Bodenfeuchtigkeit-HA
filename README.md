# 🌱 ESP32 Bodenfeuchte-Monitor

Bodenfeuchte-Sensor mit WLAN-Webserver, MQTT, Home Assistant Integration
und Telegram Bot – gebaut mit einem **ESP32 NodeMCU (diymore, USB-C)** und MicroPython.

> 🔄 Dieses Projekt ist ein Port des [Pico W Bodenfeuchte-Monitors](../Pico-Bodenfeuchtigkeit-HA)
> auf den ESP32. Alle Features sind identisch, die Hardware-Anbindung unterscheidet sich.

---

## Features

- 📊 Echtzeit-Weboberfläche mit Gauge + Kalibrierung
- 📡 MQTT-Integration für Home Assistant
- 🤖 Telegram Bot (Status, Alarme, Tagesupdate, Kalibrierung)
- 🔧 Kalibrierung per Web, Telegram und Home Assistant
- 💾 Kalibrierung wird dauerhaft gespeichert (`calibration.json`)
- 📈 Mittelwert aus 10 Messungen für stabile Werte
- ⏱ Effizient: Sensor-Update nur alle 10 Minuten
- 🔴 Alarm bei Trockenheit UND Staunässe
- 🚀 Automatisches Installations-Script

---

## Hardware

| Bauteil | Bezug | Preis |
|---|---|---|
| ESP32 NodeMCU (diymore, USB-C, CH340) | Amazon B0D9BTQRYT | ~8€ |
| Kapazitiver Feuchtigkeitssensor | AliExpress | ~1€ |
| USB-C Kabel | - | - |

### ⚠️ Wichtig: ADC-Pin Auswahl beim ESP32

Der ESP32 hat zwei ADC-Einheiten:
- **ADC1** (GPIO32–39): Funktioniert immer, auch bei aktivem WiFi ✅
- **ADC2** (GPIO0,2,4,12–15,25–27): **Nicht nutzbar bei aktivem WiFi** ❌

→ Wir verwenden **GPIO36 (VP/SVP)** = ADC1, Kanal 0.

### Verdrahtung

```
Sensor          ESP32 NodeMCU
──────          ─────────────
AOUT    →       GPIO36 (VP)
VCC     →       3V3
GND     →       GND
```

### ADC-Auflösung

| Board      | Auflösung | Wertebereich |
|------------|-----------|--------------|
| Pico W     | 16-bit    | 0 – 65535    |
| ESP32      | 12-bit    | 0 – 4095     |

Typische Rohwerte beim kapazitiven Sensor:

| Zustand        | Pico W  | ESP32   |
|----------------|---------|---------|
| Trocken (Luft) | ~52000  | ~3500   |
| Nass (Wasser)  | ~21000  | ~1000   |

---

## Schnellstart (empfohlen)

### 1. MicroPython auf ESP32 flashen

1. [MicroPython .bin für ESP32 herunterladen](https://micropython.org/download/ESP32_GENERIC/)
2. `esptool` installieren:
   ```bash
   pip install esptool
   ```
3. Flash löschen:
   ```bash
   esptool.py --chip esp32 --port COM3 erase_flash
   ```
   *(Linux/Mac: `/dev/ttyUSB0` statt `COM3`)*
4. MicroPython flashen:
   ```bash
   esptool.py --chip esp32 --port COM3 --baud 460800 write_flash -z 0x1000 esp32-XXXXXXXX.bin
   ```

### 2. Telegram Bot anlegen

1. Telegram öffnen → **@BotFather** suchen und anschreiben
2. `/newbot` senden → Name und Username vergeben
3. **Token** notieren:
   ```
   7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. Bot-Befehle registrieren – `/setcommands` bei BotFather:
   ```
   test - Sensorwert abfragen
   status - Gleich wie test
   info - Systeminformationen
   alarm - Alarmschwelle anzeigen
   cal_dry - Trocken kalibrieren
   cal_wet - Nass kalibrieren
   cal_info - Kalibrierung anzeigen
   hilfe - Alle Befehle
   ```

### 3. Telegram Chat-ID herausfinden

1. Deinen Bot in Telegram suchen → `/start` schicken
2. Diese URL im Browser öffnen (Token einsetzen):
   ```
   https://api.telegram.org/botDEIN_TOKEN/getUpdates
   ```
3. Die Zahl bei `"id"` notieren – das ist deine Chat-ID.

### 4. Installations-Script ausführen

```bash
# Repository klonen
git clone https://github.com/dein-name/ESP32-Bodenfeuchtigkeit-HA
cd ESP32-Bodenfeuchtigkeit-HA

# Script starten (Python 3 erforderlich)
python install.py
```

Das Script:
- installiert `mpremote` automatisch falls nötig
- fragt alle Zugangsdaten interaktiv ab
- generiert `config.py`
- installiert `umqtt.simple` auf dem ESP32
- überträgt alle Dateien auf den ESP32
- startet den ESP32 neu

---

## Manuelle Installation

### 1. mpremote installieren
```bash
pip install mpremote
```

### 2. umqtt.simple auf ESP32 installieren
```bash
python -m mpremote connect auto exec "import mip; mip.install('umqtt.simple')"
```

### 3. config.py anpassen
```python
WIFI_SSID        = "Dein WLAN"
WIFI_PASSWORD    = "Dein Passwort"
MQTT_BROKER      = "192.168.x.x"
TELEGRAM_TOKEN   = "Dein Bot Token"
TELEGRAM_CHAT_ID = 123456789
```

### 4. Dateien übertragen
```bash
python -m mpremote connect auto fs cp config.py :config.py
python -m mpremote connect auto fs cp main.py :main.py
```

---

## Home Assistant Integration

### 1. Mosquitto Broker installieren
```
Einstellungen → Add-ons → Mosquitto broker → Installieren → Starten
```

### 2. MQTT Integration einrichten
```
Einstellungen → Integrationen → + Integration → MQTT
→ "Offizielle Mosquitto App verwenden"
```

### 3. Packages-Ordner einrichten

In `configuration.yaml` einmalig eintragen:
```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 4. ha_config.yaml kopieren

```
/config/
├── configuration.yaml
├── packages/               ← Ordner anlegen
│   └── ha_config.yaml      ← Datei hier ablegen
```

### 5. HA neu starten
```
Einstellungen → System → Neu starten
```

Danach erscheinen unter **Einstellungen → Entitäten**:
```
sensor.bodenfeuchte_garten
sensor.bodenfeuchte_raw
sensor.bodenfeuchte_uhrzeit
sensor.kalibrierung_trocken
sensor.kalibrierung_nass
button.trocken_kalibrieren
button.nass_kalibrieren
```

### 6. Dashboard-Karte hinzufügen

Beliebiges Dashboard → Karte hinzufügen → YAML-Editor:
```yaml
type: vertical-stack
cards:
  - type: gauge
    entity: sensor.bodenfeuchte_garten
    name: Bodenfeuchte Garten
    min: 0
    max: 100
    needle: true
    severity:
      green: 50
      yellow: 25
      red: 0

  - type: entities
    title: Kalibrierung
    entities:
      - sensor.kalibrierung_trocken
      - sensor.kalibrierung_nass
      - sensor.bodenfeuchte_raw
      - sensor.bodenfeuchte_uhrzeit
      - button.trocken_kalibrieren
      - button.nass_kalibrieren
```

---

## Kalibrierung

### Option 1 – Weboberfläche
```
http://<ESP32-IP> → Kalibrierung-Karte
```
1. Sensor trocken in Luft halten → **Trocken setzen** klicken
2. Sensor in Wasserglas tauchen → **Nass setzen** klicken

### Option 2 – Telegram Bot
```
/cal_dry   → Sensor muss trocken in Luft sein
/cal_wet   → Sensor muss in Wasser sein
/cal_info  → Aktuelle Werte anzeigen
```

### Option 3 – Home Assistant
```
Einstellungen → Entitäten → Button
→ "Trocken kalibrieren" / "Nass kalibrieren"
```

---

## Telegram Bot Befehle

| Befehl | Funktion |
|---|---|
| `/test` | Aktuellen Sensorwert abfragen |
| `/status` | Gleich wie `/test` |
| `/info` | Uptime, MQTT, Intervall, Board-Info |
| `/alarm` | Alarmschwellen anzeigen |
| `/cal_dry` | Trocken kalibrieren |
| `/cal_wet` | Nass kalibrieren |
| `/cal_info` | Kalibrierungswerte anzeigen |
| `/hilfe` | Alle Befehle |

---

## API Endpunkte (Webserver)

| Endpunkt | Beschreibung |
|---|---|
| `/` | Weboberfläche mit Kalibrierung |
| `/data` | JSON mit allen Sensorwerten |
| `/cal/dry` | Trocken kalibrieren |
| `/cal/wet` | Nass kalibrieren |

### JSON Beispiel `/data`
```json
{
  "moisture": 67.3,
  "raw": 1800,
  "raw_dry": 3500,
  "raw_wet": 1000,
  "unit": "%",
  "time": "08:42:11",
  "date": "14.05.2026"
}
```

---

## Dateistruktur

```
ESP32
├── config.py           ← WLAN, MQTT, Telegram, Einstellungen
├── main.py             ← Hauptscript
└── calibration.json    ← wird automatisch erstellt

PC (dieses Repository)
├── install.py          ← Installations-Script
├── config.py           ← wird von install.py generiert
├── main.py             ← Hauptscript
├── README.md
└── ha_config.yaml      ← in HA /config/packages/ ablegen
```

---

## Unterschiede zum Pico W Projekt

| Eigenschaft | Pico W | ESP32 (dieses Repo) |
|---|---|---|
| ADC-Auflösung | 16-bit (0–65535) | 12-bit (0–4095) |
| ADC-Pin | GP26 | GPIO36 (VP) |
| ADC-Methode | `adc.read_u16()` | `adc.read()` |
| Attenuation | nicht nötig | `ATTN_11DB` für 3,3V |
| LED-Pin | `"LED"` | GPIO2 |
| MicroPython Flash | .uf2 (BOOTSEL) | .bin (esptool) |
| Dual-Core | ✗ | ✅ (nicht genutzt) |
| Bluetooth | ✗ | ✅ (nicht genutzt) |

---

## Richtwerte Bodenfeuchte

| Pflanzentyp | Idealbereich | Alarm bei |
|---|---|---|
| Kakteen / Sukkulenten | 10–30 % | < 10 % |
| Zimmerpflanzen (normal) | 50–70 % | < 40 % |
| Gemüse / Kräuter | 60–80 % | < 50 % |
| Tropische Pflanzen | 70–90 % | < 60 % |

---

## Lizenz

MIT License – frei verwendbar und anpassbar.
