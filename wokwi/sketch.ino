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
// Shared runtime state: loop schedules telemetry; publishTelemetry updates
// door/temperature alarm state so transitions are emitted only once.
uint32_t lastTelemetryMs = 0;
uint32_t doorOpenedAtMs = 0;
bool doorAlarmSent = false;
bool temperatureAlarmActive = false;

/*
 * Build this device's topic path from the common namespace, device identifier,
 * and message suffix. connectMqtt uses it for status; publishAlarm and
 * publishTelemetry use it for their respective event and sample topics.
 * Returning a String keeps topic construction consistent across publishers.
 */
String topic(const char *suffix) {
  return String("cold-chain/") + DEVICE_ID + "/" + suffix;
}

/*
 * Start Wi-Fi association and wait until the simulator reports a connection.
 * setup calls this before MQTT initialization, and loop calls it after a
 * later disconnect. This implementation deliberately blocks while retrying
 * every 250 ms; MQTT and sensor work resume only after Wi-Fi is available.
 */
void connectWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
}

/*
 * Configure the broker and reconnect until the MQTT session is established.
 * setup and loop call this after Wi-Fi is available. The connect request
 * registers a QoS 1 retained "offline" Last Will on this device's status
 * topic; on success this function publishes retained "online" status. A
 * failed attempt waits two seconds before retrying. topic() supplies the
 * status path, and the PubSubClient session is subsequently serviced by loop.
 */
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

/*
 * Serialize one device-originated alarm and publish it without retaining it.
 * publishTelemetry calls this only when a temperature state changes or the
 * door-open duration first crosses its threshold. The Node-RED alarm
 * subscription consumes this topic. The function uses a fixed-size buffer
 * and topic() for the device-specific destination.
 */
void publishAlarm(const char *code, const char *message) {
  const String alarmTopic = topic("alarms");
  char payload[160];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"code\":\"%s\",\"message\":\"%s\"}",
           DEVICE_ID, code, message);
  mqttClient.publish(alarmTopic.c_str(), payload, false);
}

/*
 * Read both DHT22 values, evaluate local alarms, and publish one JSON sample.
 * loop calls this every TELEMETRY_INTERVAL_MS. Invalid sensor data is logged
 * and ends this cycle before state or MQTT payloads are changed. Valid reads
 * update the sampled door-open timer, emit temperature transition events and
 * at most one long-open-door event, then publish telemetry. Alarm publishing
 * delegates to publishAlarm(); both alarm and telemetry paths use topic().
 */
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

/*
 * Arduino entry point called once at boot. It initializes serial diagnostics,
 * configures the active-low door button, starts the DHT22, then establishes
 * Wi-Fi before MQTT so connectMqtt always has network connectivity.
 */
void setup() {
  Serial.begin(115200);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  dht.begin();
  connectWifi();
  connectMqtt();
}

/*
 * Arduino's repeated service loop. It restores Wi-Fi and then MQTT when
 * needed, services the MQTT client's keep-alive/network processing, and
 * invokes publishTelemetry at the configured interval. Unsigned subtraction
 * keeps the elapsed-time check safe across millis() rollover; the short final
 * delay yields processor time between iterations.
 */
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
