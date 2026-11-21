# Wokwi ESP32 Device

This directory contains the simulated board wiring (`diagram.json`), firmware (`sketch.ino`), and required Arduino libraries (`libraries.txt`). The DHT22 has four pins: connect `VCC` to `3V3`, `SDA` to ESP32 `D15` (GPIO 15), and `GND` to ground; leave `NC` unconnected. The door push button connects to `D27` (GPIO 27) and ground and is read with `INPUT_PULLUP`.

## Wokwi setup

1. Open the saved [Cold Chain IoT Gateway project](https://wokwi.com/projects/481333516199647233), or create an ESP32 project at `https://wokwi.com/projects/new/esp32`.
2. For a new project, copy `sketch.ino` and `diagram.json` and install each library listed in `libraries.txt`.
3. Run the simulation, adjust the DHT22 temperature or humidity, and press `D` to open or close the door. The Serial Monitor reports Wi-Fi and MQTT connection attempts.

The default sketch connects to `broker.hivemq.com:1883` through Wokwi's free
Public Gateway. It uses device ID `esp32-ccgw-dk-hb`; the local Mosquitto bridge
subscribes only to that topic namespace and forwards messages to Node-RED. Keep
the Node-RED broker host set to `mosquitto`. This route needs no Wokwi paid
plan, but HiveMQ and Wokwi's Public Gateway are shared services, the MQTT
traffic is unencrypted, and public-gateway traffic may be monitored. Use only
synthetic demo data.

## Live verification status

An earlier HTTP 503 from `wss://netwi.wokwi.com/` was not reproduced by the
standalone probe, which obtained IP `10.10.0.2` and opened TCP to
`broker.hivemq.com:1883`. The DHT22 issue was a separate wiring-definition
problem: the old `esp:15` endpoint did not produce a visible/electrical SDA
connection in Wokwi. The diagram now uses the documented
`wokwi-esp32-devkit-v1` board and `esp:D15`/`esp:D27` pin names. The recommended
`DHT sensor library for ESPx` is also in use. A sensor-only simulation now
reports `status=OK`, `temperature_c=5.00`, and `humidity_pct=55.00` repeatedly.

The latest full firmware run again received HTTP 503 during Wi-Fi association.
An earlier isolated run reached HiveMQ, so the gateway path has worked in one
test but failed in another; its cause is unknown. Valid MQTT telemetry after
the wiring fix, dashboard updates, alarms, and LWT remain unverified end to
end. The HiveMQ-to-Mosquitto bridge was separately verified using a synthetic
message.

For a reproducible isolation test that checks Wi-Fi association and outbound
TCP to HiveMQ without `PubSubClient`, use the separate
[`network-diagnostic/README.md`](network-diagnostic/README.md) sketch in a
temporary Wokwi project.

For a sensor-only check that excludes Wi-Fi and MQTT, see
[`dht-diagnostic/README.md`](dht-diagnostic/README.md).

## Firmware function map

```mermaid
flowchart TD
    Setup["setup() - called once at boot"] --> Wifi["connectWifi()"]
    Setup --> Mqtt["connectMqtt()"]
    Mqtt --> TopicStatus["topic(status)"]
    Loop["loop() - repeated by Arduino"] --> WifiCheck{"Wi-Fi connected?"}
    WifiCheck -->|no| Wifi
    Loop --> MqttCheck{"MQTT connected?"}
    MqttCheck -->|no| Mqtt
    Loop --> Pump["mqttClient.loop()"]
    Loop --> Timer{"10-second interval elapsed?"}
    Timer -->|yes| Telemetry["publishTelemetry()"]
    Telemetry --> Sensor["Read DHT22 and door pin"]
    Telemetry -->|state transition or door limit| Alarm["publishAlarm(code, message)"]
    Alarm --> AlarmTopic["topic(alarms)"]
    Telemetry --> TelemetryTopic["topic(telemetry)"]
```

| Function | Inputs and state | Calls, output, or side effects |
| --- | --- | --- |
| `topic(suffix)` | Suffix and fixed device ID | Returns `cold-chain/<device_id>/<suffix>`; used by MQTT connection and publish functions. |
| `connectWifi()` | Simulator Wi-Fi credentials | Starts association on Wokwi channel 6, reports progress, and blocks in 250 ms waits until connected; called by `setup()` and `loop()`. |
| `connectMqtt()` | Wi-Fi-connected MQTT client | Sets broker and 30 s keep-alive, registers retained QoS 1 offline LWT, logs retry state, and publishes retained online status. Called by `setup()` and `loop()`. |
| `publishAlarm(code, message)` | Alarm identifier and English description | Builds a JSON event and publishes non-retained to `topic("alarms")`; called by `publishTelemetry()`. |
| `publishTelemetry()` | DHT22 readings, door input, shared alarm state | Rejects invalid sensor reads, evaluates temperature transitions and sampled door duration, then publishes telemetry. Calls `publishAlarm()` and `topic()`. |
| `setup()` | Arduino boot lifecycle | Initializes serial, door input, DHT22, Wi-Fi, and MQTT in dependency order. |
| `loop()` | Arduino repeated lifecycle | Recovers connections, services MQTT, and schedules `publishTelemetry()` every 10 seconds. |

See [`../mosquitto/README.md`](../mosquitto/README.md) for the free bridge setup
and [`../docs/architecture.md`](../docs/architecture.md) for the full call
graph and MQTT payload contract.

## Change history

- Initial prototype: added DHT22 and door wiring, 10-second telemetry, thermal/door alarms, and retained MQTT LWT status.
- English documentation pass: translated serial errors, alarm messages, simulator labels, and code comments.
- Connectivity diagnostics: use Wokwi's documented Wi-Fi channel 6 and report Wi-Fi progress and MQTT retry state to Serial Monitor. A separate probe confirmed virtual Wi-Fi association and TCP reachability to HiveMQ.
- DHT22 wiring fix: the former `esp:15` endpoint did not connect the SDA pin in Wokwi. The board and pin references now match Wokwi's ESP32 DHT22 example, and the isolated sensor test repeatedly reads 5.00 C and 55.00% humidity.
