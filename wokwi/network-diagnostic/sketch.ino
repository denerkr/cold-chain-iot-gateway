#include <Arduino.h>
#include <WiFi.h>

namespace {
constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";
constexpr char MQTT_HOST[] = "broker.hivemq.com";
constexpr uint16_t MQTT_PORT = 1883;
constexpr uint32_t STATUS_INTERVAL_MS = 2000;

WiFiClient tcpProbe;
uint32_t lastStatusReportMs = 0;
bool brokerProbeFinished = false;

/*
 * Start association with Wokwi's documented channel 6 and print markers on
 * both sides of WiFi.begin(). setup() calls this once. The markers help
 * distinguish a call that returns from a simulator-side stall inside WiFi.
 */
void connectWifi() {
  Serial.println("PROBE: calling WiFi.begin()");
  Serial.flush();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  Serial.println("PROBE: WiFi.begin() returned");
  Serial.flush();
}

/*
 * Resolve HiveMQ and attempt one outbound TCP connection to its MQTT port.
 * loop() calls this only after WL_CONNECTED. This tests DNS/TCP reachability;
 * it does not send an MQTT CONNECT packet, credentials, or application data.
 */
void probeBrokerTcp() {
  Serial.printf("PROBE: opening TCP connection to %s:%u\n", MQTT_HOST, MQTT_PORT);
  Serial.flush();
  if (tcpProbe.connect(MQTT_HOST, MQTT_PORT)) {
    Serial.println("PROBE: TCP connection succeeded");
    tcpProbe.stop();
  } else {
    Serial.println("PROBE: TCP connection failed");
  }
  Serial.flush();
  brokerProbeFinished = true;
}
}  // namespace

/*
 * Arduino startup entry point. It opens the serial monitor, confirms that
 * user firmware is executing, and then begins the Wi-Fi association probe.
 */
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("PROBE: firmware started");
  connectWifi();
}

/*
 * Repeated diagnostic loop. It reports the Wi-Fi status every two seconds
 * and performs the HiveMQ TCP probe once when Wi-Fi reports WL_CONNECTED.
 */
void loop() {
  const uint32_t now = millis();
  const wl_status_t status = WiFi.status();
  if (now - lastStatusReportMs >= STATUS_INTERVAL_MS) {
    lastStatusReportMs = now;
    Serial.printf("PROBE: uptime_ms=%lu wifi_status=%d\n",
                  static_cast<unsigned long>(now), static_cast<int>(status));
  }

  if (status == WL_CONNECTED && !brokerProbeFinished) {
    Serial.printf("PROBE: assigned IP=%s\n", WiFi.localIP().toString().c_str());
    probeBrokerTcp();
  }
  delay(10);
}
