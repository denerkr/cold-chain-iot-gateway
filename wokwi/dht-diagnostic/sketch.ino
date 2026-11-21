#include <Arduino.h>
#include <DHTesp.h>

namespace {
constexpr uint8_t DHT_PIN = 15;
constexpr uint32_t SAMPLE_INTERVAL_MS = 2500;

DHTesp dht;
uint32_t lastSampleMs = 0;

/*
 * Read one DHT22 sample and print both its status and values. loop() calls
 * this on a timer so sensor diagnostics run without Wi-Fi or MQTT dependencies.
 */
void reportDhtReading() {
  const TempAndHumidity reading = dht.getTempAndHumidity();
  const String status = dht.getStatusString();
  if (dht.getStatus() != DHTesp::ERROR_NONE) {
    Serial.printf("DHT_DIAG: status=%s\n", status.c_str());
    return;
  }

  Serial.printf("DHT_DIAG: status=%s temperature_c=%.2f humidity_pct=%.2f\n",
                status.c_str(), reading.temperature, reading.humidity);
}
}  // namespace

/*
 * Initialize serial output and the ESP32-specific DHT22 driver. The sensor
 * data line must be wired to the board's D15 pin; VCC and GND are also needed.
 */
void setup() {
  Serial.begin(115200);
  dht.setup(DHT_PIN, DHTesp::DHT22);
  Serial.println("DHT_DIAG: sensor-only test started");
}

/*
 * Sample the DHT22 every 2.5 seconds, allowing the sensor's measurement
 * interval to elapse, and avoid involving Wi-Fi or MQTT in this test.
 */
void loop() {
  const uint32_t now = millis();
  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    reportDhtReading();
  }
  delay(10);
}
