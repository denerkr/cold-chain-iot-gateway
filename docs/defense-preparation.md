# Presentation Defense Preparation

Use the answers below to explain what the prototype does and, just as
importantly, what the current evidence does not establish. The design diagrams
and message contract are in [`architecture.md`](architecture.md).

## Likely questions

### Is this a real cold-chain monitoring system?

No. The ESP32, DHT22, and door switch are simulated in Wokwi. The Python
performance model is synthetic and does not measure a physical sensor, radio,
broker, or transport route. A production system would need calibrated
hardware, environmental validation, and operational safety procedures.

### What makes the design distributed?

The device firmware, MQTT broker, Mosquitto bridge, and Node-RED flow are
separate components communicating asynchronously over MQTT. The broker
decouples the publisher from subscribers; the bridge relays one topic
namespace between the public broker and the local broker.

### Why MQTT instead of direct HTTP or CoAP?

The assignment requires Node-RED and either MQTT or CoAP. MQTT's
publish/subscribe model fits periodic telemetry and events, permits multiple
subscribers, and provides broker-managed retained status and Last Will
behavior. This prototype does not claim MQTT is universally superior to CoAP.

### What does the Last Will do, and how long does it take?

The ESP32 includes a retained QoS 1 `offline` will in its MQTT CONNECT packet.
If the broker detects an unexpected loss, it publishes that status on the
device's status topic. With a 30-second keep-alive, roughly 45 seconds is a
common 1.5-times estimate, not a guaranteed deadline or a measured result.
An orderly disconnect is different from a sudden failure.

### Does QoS 1 protect every message?

No. The status and LWT use QoS 1. `PubSubClient` publishes telemetry and
device alarms at QoS 0. A subscriber asking for QoS 1 cannot raise a
publisher's QoS. A production design should select QoS per message class,
handle duplicates, and define persistence and retry behavior.

### Is the public MQTT route secure?

No. The HiveMQ demo broker uses plaintext MQTT on port 1883 without
authentication, and Wokwi warns that Public Gateway traffic may be monitored.
The bridge's topic filter limits what it forwards but is not access control.
Only synthetic, non-sensitive data belongs on this route. Production use would
require an authenticated broker, TLS, per-device authorization, and secret
management.

### Why is HiveMQ between Wokwi and local Node-RED?

Wokwi's free Public Gateway supports outbound Internet connections but cannot
reach services on the developer's local computer. The local Mosquitto broker
therefore subscribes to this project's namespace on HiveMQ and forwards
matching messages to Node-RED. The local broker remains bound to loopback.
Wokwi's Private Gateway could reach local services directly, but it requires a
paid plan.

### Has the live Wokwi-to-Node-RED path been demonstrated?

Not fully. A standalone Wokwi probe associated with the Public Gateway,
received IP `10.10.0.2`, and opened TCP to HiveMQ. We found that the old diagram
did not electrically connect the DHT22 SDA pin because it referenced `esp:15`
instead of the board's `esp:D15` pin. The diagram and ESP32-specific DHT library
are corrected; an isolated sensor test repeatedly read 5.00 C and 55.00%
humidity. The latest full firmware run received HTTP 503, so post-fix MQTT
telemetry, dashboard updates, alarms, and LWT are not yet verified. The bridge
was separately verified with a synthetic message. An earlier isolated network
probe reached HiveMQ, but the latest full run failed at the gateway; the cause
remains unknown. The offline Python simulator is not evidence of live MQTT
delivery.

### How are temperature and door alarms generated?

The firmware and Node-RED both evaluate the 2-8 C temperature range and the
30-second door-open rule. The device publishes its alarm events to MQTT;
Node-RED's locally detected alarms go directly to the dashboard. The door
rule is evaluated on telemetry samples, so the observed trigger may be late
by up to one sampling interval plus network delay. Independent evaluators
can also produce duplicate indications; a production system should define
one authoritative alarm source or deduplicate events by ID.

### What do the performance charts prove?

They summarize the seeded Python model's assumptions, such as message loss,
latency, alarm timing, and estimated LWT delay. They are repeatable synthetic
experiments, not benchmarks of HiveMQ, Mosquitto, Wokwi, or a physical
network. The seed-sweep histogram counts independent trials, not MQTT
messages, and a per-trial P95 latency is not a confidence interval.

### Is event history durable?

No. The dashboard provides live widgets and chart history but this prototype
does not add a time-series database or durable event store. For operational
use, telemetry and alarms should be persisted with timestamps, device
identity, and a documented retention policy.

## Improvements beyond the teaching prototype

1. Re-run the Wokwi public-gateway check and capture evidence of telemetry,
   threshold alarms, dashboard updates, and abrupt-disconnect LWT.
2. Use TLS, broker authentication, topic ACLs, and unique per-device
   credentials before sending anything sensitive.
3. Add message sequence numbers, timestamps, alarm IDs, duplicate handling,
   and durable storage for auditability.
4. Replace blocking reconnect loops with bounded backoff and an explicit
   offline/buffered state; test broker and Wi-Fi outages.
5. Calibrate and validate physical sensors, power behavior, enclosure, and
   alert thresholds before making any safety or compliance claim.
6. Document measured network experiments separately from synthetic
   Monte Carlo results.
