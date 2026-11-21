#include <Arduino.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>

namespace {
constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";
constexpr char MQTT_HOST[] = "broker.hivemq.com";
constexpr uint16_t MQTT_PORT = 1883;
constexpr char DEVICE_ID[] = "esp32-cold-chain";
constexpr uint8_t DHT_PIN = 15;
constexpr uint8_t DOOR_PIN = 27;
constexpr uint8_t DHT_TYPE = DHT22;
constexpr uint32_t TELEMETRY_INTERVAL_MS = 10000;
constexpr float MIN_TEMPERATURE_C = 2.0;
constexpr float MAX_TEMPERATURE_C = 8.0;
constexpr uint32_t MAX_DOOR_OPEN_MS = 30000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
DHT dht(DHT_PIN, DHT_TYPE);
uint32_t lastTelemetryMs = 0;
uint32_t doorOpenedAtMs = 0;
bool doorAlarmSent = false;
bool temperatureAlarmActive = false;

// Build the device-specific MQTT topic for the requested message type.
String topic(const char *suffix) {
  return String("cold-chain/") + DEVICE_ID + "/" + suffix;
}

// Connect the ESP32 to the simulator-provided wireless network.
void connectWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
}

// Connect to MQTT and register a retained offline last will for this device.
void connectMqtt() {
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setKeepAlive(30);

  while (!mqttClient.connected()) {
    const String clientId =
        String(DEVICE_ID) + "-" + String(static_cast<uint32_t>(ESP.getEfuseMac()), HEX);
    const String statusTopic = topic("status");
    const bool connected = mqttClient.connect(
        clientId.c_str(), statusTopic.c_str(), 1, true, "offline");
    if (connected) {
      mqttClient.publish(statusTopic.c_str(), "online", true);
    } else {
      delay(2000);
    }
  }
}

// Publish one JSON alarm event on the device alarm topic.
void publishAlarm(const char *code, const char *message) {
  const String alarmTopic = topic("alarms");
  char payload[160];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"code\":\"%s\",\"message\":\"%s\"}",
           DEVICE_ID, code, message);
  mqttClient.publish(alarmTopic.c_str(), payload, false);
}

// Read sensors, apply temperature and door rules, and publish one telemetry sample.
void publishTelemetry() {
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Error: invalid DHT22 reading");
    return;
  }

  const bool doorOpen = digitalRead(DOOR_PIN) == LOW;
  const uint32_t now = millis();
  if (doorOpen && doorOpenedAtMs == 0) {
    doorOpenedAtMs = now;
    doorAlarmSent = false;
  } else if (!doorOpen) {
    doorOpenedAtMs = 0;
    doorAlarmSent = false;
  }

  const bool temperatureOutOfRange =
      temperature < MIN_TEMPERATURE_C || temperature > MAX_TEMPERATURE_C;
  if (temperatureOutOfRange && !temperatureAlarmActive) {
    publishAlarm("temperature_excursion", "Temperature outside the 2 to 8 C range");
  } else if (!temperatureOutOfRange && temperatureAlarmActive) {
    publishAlarm("temperature_restored", "Temperature returned to the 2 to 8 C range");
  }
  temperatureAlarmActive = temperatureOutOfRange;

  if (doorOpen && !doorAlarmSent && now - doorOpenedAtMs >= MAX_DOOR_OPEN_MS) {
    publishAlarm("door_open_too_long", "Door has been open for more than 30 seconds");
    doorAlarmSent = true;
  }

  char payload[192];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"temperature_c\":%.2f,"
           "\"humidity_pct\":%.2f,\"door_open\":%s,\"uptime_s\":%lu}",
           DEVICE_ID, temperature, humidity, doorOpen ? "true" : "false",
           static_cast<unsigned long>(now / 1000));
  const String telemetryTopic = topic("telemetry");
  if (!mqttClient.publish(telemetryTopic.c_str(), payload, false)) {
    Serial.println("Error: failed to publish telemetry");
  }
}
}  // namespace

// Initialize serial logging, the door input, the sensor, Wi-Fi, and MQTT.
void setup() {
  Serial.begin(115200);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  dht.begin();
  connectWifi();
  connectMqtt();
}

// Maintain Wi-Fi and MQTT connections and publish telemetry on schedule.
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
  if (!mqttClient.connected()) {
    connectMqtt();
  }
  mqttClient.loop();

  const uint32_t now = millis();
  if (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = now;
    publishTelemetry();
  }
  delay(10);
}
