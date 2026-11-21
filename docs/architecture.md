# Architecture and Function Call Paths

This document explains how component functions exchange messages. Names and payload fields are part of the teaching prototype's interface; update the firmware, Node-RED flow, simulator, tests, and docs together if that interface changes.

## End-to-end sequence

```mermaid
sequenceDiagram
    autonumber
    participant Sensor as DHT22 and door switch
    participant Firmware as ESP32 firmware
    participant PublicBroker as HiveMQ public demo broker
    participant Bridge as Local Mosquitto bridge
    participant LocalBroker as Local Mosquitto listener
    participant Flow as Node-RED telemetry flow
    participant AlarmFlow as Node-RED alarm/status flows
    participant UI as Dashboard

    Firmware->>PublicBroker: CONNECT with 30 s keep-alive and retained QoS 1 offline LWT
    Firmware->>PublicBroker: PUBLISH status = online (retained)
    loop Every 10 seconds
        Firmware->>Sensor: Read temperature, humidity, and door state
        Sensor-->>Firmware: Sensor readings
        opt Temperature changes into or out of 2-8 C compliance
            Firmware->>PublicBroker: PUBLISH alarm event (QoS 0, not retained)
        end
        opt Door remains open for at least 30 seconds
            Firmware->>PublicBroker: PUBLISH door alarm (QoS 0, not retained)
        end
        Firmware->>PublicBroker: PUBLISH JSON telemetry (QoS 0, not retained)
        PublicBroker-->>Bridge: Deliver matching project namespace
        Bridge->>LocalBroker: Forward matching PUBLISH
        LocalBroker-->>Flow: Deliver cold-chain/+/telemetry
        Flow->>Flow: Parse JSON and validate required fields
        Flow->>Flow: Update per-device alarm and door-duration context
        par Valid telemetry
            Flow-->>UI: Update temperature gauge and history
            Flow-->>UI: Update humidity gauge and history
            Flow-->>UI: Update door indicator
        and Backend-detected alarms
            Flow-->>AlarmFlow: Send alarm messages directly to formatter
            AlarmFlow-->>UI: Update latest-event indicator
        end
        PublicBroker-->>Bridge: Deliver matching device alarm
        Bridge->>LocalBroker: Forward alarm PUBLISH
        LocalBroker-->>AlarmFlow: Deliver device alarm
        AlarmFlow->>AlarmFlow: Parse and validate the event
    end
    opt Subscriber starts or device status changes
        PublicBroker-->>Bridge: Deliver retained or updated device status
        Bridge->>LocalBroker: Forward status PUBLISH
        LocalBroker-->>AlarmFlow: Deliver retained or updated device status
        AlarmFlow->>AlarmFlow: Validate status topic and payload
        AlarmFlow-->>UI: Update gateway indicator
    end
    Note over Firmware,PublicBroker: Abrupt disconnect: HiveMQ publishes the registered offline LWT
    PublicBroker-->>Bridge: Deliver offline status
    Bridge->>LocalBroker: Forward retained status PUBLISH
    LocalBroker-->>AlarmFlow: Deliver offline status
    AlarmFlow-->>UI: Show the gateway as offline
```

The free end-to-end route is **Wokwi -> HiveMQ -> inbound Mosquitto bridge ->
local Mosquitto -> Node-RED**. Wokwi's Public Gateway provides outbound
Internet access but cannot reach local services. The bridge subscribes only to
`cold-chain/esp32-ccgw-dk-hb/#`; the local Node-RED MQTT configuration
continues to use `mosquitto:1883` and subscribes to the usual wildcard topics.
The local broker listener remains loopback-bound on the host. This route uses a
shared, unencrypted public broker and is only suitable for synthetic, non-secret
classroom data.

## Observed live verification status

An earlier Wokwi Public Gateway WebSocket attempt (`wss://netwi.wokwi.com/`)
returned HTTP 503. In later tests, a standalone ESP32 probe associated with
Wokwi's virtual Wi-Fi, received IP `10.10.0.2`, and opened TCP to HiveMQ on port
1883. The main firmware also connected to Wi-Fi and MQTT, but repeatedly
reported invalid DHT22 readings. The 503 was not reproduced, and its cause is
unknown; the current evidence does not support attributing it solely to a
persistent gateway outage. The HiveMQ-to-local-Mosquitto bridge separately
forwarded a synthetic test message. Valid device telemetry, device alarms,
dashboard updates, and abrupt-disconnect LWT remain unverified end to end.

## Firmware call graph

```mermaid
flowchart TD
    Setup["setup()"] --> Serial["Serial.begin()"]
    Setup --> DoorPin["pinMode(DOOR_PIN, INPUT_PULLUP)"]
    Setup --> DHTInit["dht.begin()"]
    Setup --> WiFiConnect["connectWifi()"]
    WiFiConnect --> WiFiBegin["WiFi.begin(..., channel 6) and report status"]
    Setup --> MQTTConnect["connectMqtt()"]
    MQTTConnect --> BrokerConfig["setServer() and setKeepAlive(30)"]
    MQTTConnect --> LWT["mqttClient.connect(... status topic, QoS 1, retained offline)"]
    MQTTConnect --> Online["publish retained online status"]
    Loop["loop()"] --> CheckWiFi["Check Wi-Fi and call connectWifi() if disconnected"]
    Loop --> CheckMQTT["Check MQTT and call connectMqtt() if disconnected"]
    Loop --> Pump["mqttClient.loop()"]
    Loop --> Timer{"10-second interval elapsed?"}
    Timer -->|yes| PublishTelemetry["publishTelemetry()"]
    PublishTelemetry --> ReadSensors["dht.readTemperature() and dht.readHumidity()"]
    PublishTelemetry --> ReadDoor["digitalRead(DOOR_PIN)"]
    PublishTelemetry --> ThermalRule{"Thermal state changed?"}
    ThermalRule -->|yes| Alarm["publishAlarm(code, message)"]
    PublishTelemetry --> DoorRule{"Door open for 30 seconds?"}
    DoorRule -->|yes| Alarm
    Alarm --> Topic["topic('alarms')"]
    PublishTelemetry --> Telemetry["topic('telemetry') and MQTT publish"]
```

| Function | Inputs / state | Side effects and caller |
| --- | --- | --- |
| `topic(suffix)` | A topic suffix and the fixed device identifier | Returns a `cold-chain/<device_id>/<suffix>` string to MQTT publishers. |
| `connectWifi()` | Wi-Fi credentials | Starts association on Wokwi channel 6, prints progress, and blocks until Wi-Fi is connected; called from `setup()` and `loop()`. |
| `connectMqtt()` | Configured MQTT client and device identifier | Configures keep-alive, connects with a retained QoS 1 offline will, logs failed retry state, then publishes retained online status. Called at startup and after disconnect. |
| `publishAlarm(code, message)` | Alarm identifier and English description | Encodes a JSON event and publishes to the non-retained alarm topic at the client's publish QoS. Called by sensor rules. |
| `publishTelemetry()` | DHT22 values, digital door pin, elapsed uptime | Tracks door-open duration and thermal state, emits any transition alarms, then publishes one JSON sample. |
| `setup()` | ESP32 startup | Initializes serial, input pin, DHT22, Wi-Fi, and MQTT once. |
| `loop()` | Arduino scheduler | Restores Wi-Fi/MQTT if needed, services MQTT keep-alive, and schedules telemetry. |

## MQTT contract

| Topic | Publisher | Payload | QoS / retain |
| --- | --- | --- | --- |
| `cold-chain/<device_id>/telemetry` | ESP32 | `device_id`, `temperature_c`, `humidity_pct`, `door_open`, `uptime_s` | Firmware publishes QoS 0, not retained |
| `cold-chain/<device_id>/alarms` | ESP32 | `device_id`, `code`, `message` | Firmware publishes QoS 0, not retained |
| `cold-chain/<device_id>/status` | ESP32 and its broker will | `online` or `offline` | QoS 1, retained |

The Node-RED subscription requests QoS 1, but MQTT delivery cannot exceed the publisher's QoS. The Python simulator uses a separate synthetic CSV/JSON schema and never publishes to a broker.

Example firmware telemetry payload:

```json
{
  "device_id": "esp32-ccgw-dk-hb",
  "temperature_c": 5.0,
  "humidity_pct": 55.0,
  "door_open": false,
  "uptime_s": 10
}
```

Example device alarm payload:

```json
{
  "device_id": "esp32-ccgw-dk-hb",
  "code": "temperature_excursion",
  "message": "Temperature outside the 2 to 8 C range"
}
```

Backend-detected dashboard events add a UTC `timestamp`; the device alarm payload intentionally remains a small event record.

## Node-RED call/data-flow

```mermaid
flowchart LR
    TelemetryMQTT["MQTT In: cold-chain/+/telemetry"] --> Validate["Function: validate-and-route"]
    Validate -->|output 1: temperature| TempGauge["Temperature gauge"]
    Validate -->|output 2: humidity| HumGauge["Humidity gauge"]
    Validate -->|output 3: temperature, device topic| TempChart["Temperature history"]
    Validate -->|output 4: humidity, device topic| HumChart["Humidity history"]
    Validate -->|output 5: OPEN/CLOSED| DoorText["Door status"]
    Validate -->|output 6: one or more local alarms| Format["Function: format-alarm"]
    DeviceAlarms["MQTT In: cold-chain/+/alarms"] --> Format
    Format --> Latest["Latest-event dashboard text"]
    DeviceStatus["MQTT In: cold-chain/+/status"] --> Gateway["Gateway status dashboard text"]
```

`validate-and-route` parses a JSON string when necessary, rejects invalid JSON and missing/incorrect sensor fields, then emits five dashboard data messages. Its per-device Node-RED context stores the previous thermal alarm state, door-open timestamp, and whether an open-door alarm was already raised. It emits an alarm only on a thermal state transition or the first telemetry sample observed after the 30-second door threshold. If both rules trigger on one sample, output 6 contains both alarm messages.

Backend alarm messages go from output 6 directly to `format-alarm`; they are not published to MQTT. Device-originated alarm messages arrive independently through the alarm subscription. `format-alarm` accepts either a decoded JSON object or a JSON string, validates its `code` and `message`, and formats the last-event widget. `gateway-status` displays the device identifier from the topic and the retained status payload.

## Offline simulation and aggregation flow

```mermaid
flowchart TD
    Main["main()"] --> Experiment["run_experiment()"]
    Main -.->|sensitivity flag| Sensitivity["run_sensitivity_analysis()"]

    Experiment -->|each seed; first run writes detailed files| Trial["run_simulation()"]
    Trial --> EventTime["_event_timestamp()"]
    Trial --> DegreeMinutes["_temperature_excursion_degree_minutes()"]
    Trial --> Percentile["percentile()"]
    Trial -->|when write_reports is true| SingleCharts["_write_performance_chart()<br/>_write_system_performance_chart()"]
    SingleCharts --> Percentile
    Trial --> TrialMetrics["Per-trial delivery, latency, alarm, and exposure metrics"]

    Experiment --> Aggregate["_aggregate_metric()"]
    TrialMetrics --> Aggregate
    Experiment --> SweepCharts["_write_seed_sweep_chart()<br/>_write_alarm_response_chart()"]
    Experiment --> SweepJSON["seed_sweep_metrics.json"]
    Aggregate -.->|aggregated values| SweepCharts
    Aggregate -.->|summary data| SweepJSON

    Sensitivity -->|each drop rate x seed; no trial files| Trial
    Sensitivity --> Aggregate
    Sensitivity --> NetworkChart["_write_network_sensitivity_chart()"]
    Sensitivity --> KeepaliveChart["_write_keepalive_sensitivity_chart()"]
    Sensitivity --> SensitivityJSON["Network and LWT sensitivity JSON"]
    Aggregate -.->|scenario summaries| NetworkChart
    Aggregate -.->|summary data| SensitivityJSON
```

`run_simulation` uses a local seeded pseudo-random generator. With
`write_reports=True`, it writes detailed files into the requested output
directory; `run_experiment` enables that only for its first seed, while all
other seeds still return metrics. Sensitivity runs disable per-trial output.
`percentile` uses the nearest-rank definition; `_aggregate_metric` computes
`mean +/- 1.96 * sample_standard_deviation / sqrt(n)` as a descriptive,
approximate interval.

## Simulation test call graph

```mermaid
flowchart TD
    ArtifactTest["test_simulation_emits_alarm_events_and_performance_artifacts"] --> Trial["run_simulation()"]
    ReproTest["test_simulation_is_reproducible_with_same_seed"] --> Trial
    ZeroDropTest["test_zero_drop_rate_delivers_all_generated_messages"] --> Trial
    DropValidationTest["test_simulation_rejects_invalid_drop_rates"] --> Trial

    SeedTest["test_seed_sweep_aggregates_independent_runs"] --> Experiment["run_experiment()"]
    InvalidRunTest["test_seed_sweep_rejects_non_positive_run_count"] --> Experiment
    SingleSeedTest["test_single_seed_sweep_omits_confidence_interval"] --> Experiment
    DropValidationTest --> Experiment

    IntervalTest["test_non_negative_metric_confidence_interval_does_not_cross_zero"] --> Aggregate["_aggregate_metric()"]
    SensitivityTest["test_sensitivity_analysis_writes_network_and_lwt_results"] --> Sensitivity["run_sensitivity_analysis()"]
    Experiment --> Trial
    Experiment --> Aggregate
    Sensitivity --> Trial
    Sensitivity --> Aggregate
```

The test suite exercises both public orchestration paths and the interval
boundary helper. Each test uses isolated temporary output directories and
asserts either returned values, validation behavior, or generated artifacts.

## Cross-component change checklist

When modifying sensor fields or topic names, update each relevant item:

1. Firmware payload construction and topic helper usage in `wokwi/sketch.ino`.
2. Node-RED topic subscriptions, validation, routes, and dashboard labels in `node-red/flows.json`.
3. Simulator sample/event records and metric aggregation in `simulation/run_simulation.py`.
4. Assertions in `tests/test_simulation.py`.
5. The MQTT table above, the root README, and affected component `README.md` files.
