# config.py – generiert von install.py (ESP32 NodeMCU)

# WLAN
WIFI_SSID     = "FRITZ!Box 7560 ME"
WIFI_PASSWORD = "50517880555497667758"

# MQTT
MQTT_BROKER    = "192.168.178.183"
MQTT_PORT      = 1883
MQTT_CLIENT_ID = "esp32_soil_sensor"
MQTT_TOPIC     = b"home/garden/soil_moisture"
MQTT_CMD_TOPIC = b"home/garden/soil_moisture/cmd"
MQTT_CAL_TOPIC = b"home/garden/soil_moisture/calibration"
MQTT_USER      = "mqtt_esp32"
MQTT_PASSWORD  = "ichundich102"

# Telegram
TELEGRAM_TOKEN   = "8755316025:AAEkcDDI7MHDXembjxwHkY6U1WVVqi_1RnU"
TELEGRAM_CHAT_ID = 6471007598

# Zeitzone (Deutschland: Winter=1, Sommer=2)
UTC_OFFSET = 2

# Tagesupdate
MORNING_HOUR   = 8
MORNING_MINUTE = 0

# Sensor-Startwerte (ESP32 ADC 12-bit: 0–4095)
RAW_DRY = 3500
RAW_WET  = 1000

# Alarm
ALARM_THRESHOLD = 30
ALARM_WET       = 90
ALARM_COOLDOWN  = 3600

# Intervalle
PUBLISH_INTERVAL = 600
COMMAND_INTERVAL = 10
SAMPLES          = 10
