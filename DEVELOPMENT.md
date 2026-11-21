# Development Notes and Change History

This file records the design intent and development context needed to continue the project without reconstructing decisions from code alone. Detailed component call paths are in [`docs/architecture.md`](docs/architecture.md); each component directory also has a `README.md`.

## Design decisions

- **MQTT topic contract:** `cold-chain/<device_id>/telemetry`, `cold-chain/<device_id>/alarms`, and `cold-chain/<device_id>/status` separate measurements, events, and availability. Keep `device_id` stable and unique per simulated node.
- **Alarm range and cadence:** temperature compliance is 2-8 C; telemetry is published every 10 seconds; door alarms begin after 30 seconds. Backend door timing is based on telemetry arrival, so detection occurs on the first sample after the threshold rather than at an exact 30-second instant.
- **Last Will:** the ESP32, not Node-RED, owns its retained QoS 1 `offline` will. The broker's detection interval depends on its keep-alive handling; 1.5 times 30 seconds is an estimate, not a measured guarantee.
- **Two rule evaluators:** firmware reports local alarms and Node-RED independently evaluates telemetry. Backend alarms are routed directly to the dashboard rather than republished to MQTT, avoiding a publish/subscribe feedback loop. Device-originated alarms remain available on the MQTT alarm topic.
- **Free end-to-end broker route:** the Compose stack supplies a loopback-only local Mosquitto broker for Node-RED. Wokwi's free Public Gateway cannot reach the local computer, so the ESP32 publishes to HiveMQ and Mosquitto bridges inbound only the unique project topic namespace. Do not expose the local listener or send sensitive data; the public broker and gateway are shared and unencrypted.
- **Offline model:** the Python simulator intentionally needs no broker, Docker, Wokwi, or hardware. Synthetic network, alarm, and LWT metrics are explicitly labeled as simulated and must not be presented as measurements.
- **Monte Carlo runs:** `--runs N` evaluates sequential independent seeds `base_seed` through `base_seed + N - 1`. Aggregates include the individual values, mean, sample deviation, and a normal-approximation 95% interval. A single seed cannot estimate an interval.
- **Operational metrics:** thermal compliance uses only delivered sensor samples. Degree-minutes are integrated over contiguous 10-second received samples; missing intervals are excluded to avoid inventing observations. Alarm-delay distributions separate the injected fault start/threshold from the model's additional sampling and network delay.
- **Sensitivity scenarios:** packet loss is compared at 0%, 1%, 5%, and 10% using the same seed sequence. Because changing a drop decision changes later pseudorandom draws in the current single-stream model, scenario values are descriptive rather than paired sample-by-sample comparisons. Keep-alive/LWT points use the theoretical `1.5 x keep-alive` assumption, not broker timing.
- **Reproducibility:** the default base seed is `410103`. Preserve this seed and simulation constants to reproduce a specific version's outputs.

## Component responsibilities

| Directory or file | Responsibility |
| --- | --- |
| `wokwi/` | ESP32 firmware, wiring diagram, and simulator library declarations |
| `mosquitto/` | Local demo broker configuration |
| `node-red/` | MQTT subscriptions, input validation, alarm rules, and Dashboard flow |
| `simulation/` | Deterministic trial model, multi-seed statistics, and chart generation |
| `tests/` | Behavioral and artifact-output regression tests for the simulator |
| `reports/` | Generated example outputs; regenerate from the documented CLI |
| `docs/architecture.md` | Cross-component message and function-call diagrams |

## Change history

### Initial prototype

- Added the ESP32/DHT22/door-button Wokwi example and structured MQTT topics.
- Added retained device status and abrupt-disconnect Last Will behavior.
- Added local Mosquitto and Node-RED Dashboard configurations, including thermal and door rules.
- Added an offline synthetic telemetry simulator and initial charts.

### English documentation and multi-seed analysis

- Standardized user-facing strings, chart labels, dashboard text, and code comments to English.
- Added `--runs` to evaluate sequential random seeds, plus metric distributions and approximate confidence intervals.
- Added per-directory implementation notes and a detailed Mermaid architecture/function-flow reference for future maintainers.
- Removed Node-RED MQTT broker birth/close/will messages from the device availability topic. The device alone publishes its own status, so Node-RED's lifecycle cannot falsely mark the device online or offline.
- Routed backend-generated alarms directly to the dashboard instead of echoing them through MQTT; allowed simultaneous thermal and door alarms to reach the formatter together.

### Operational and sensitivity analysis

- Added sample-based temperature compliance, excursion degree-minutes, excursion-window message coverage, and temperature/door alarm response delays to trial and seed-sweep metrics.
- Added packet-loss scenarios to expose the relationship between modeled delivery loss and alarm behavior.
- Added a separate theoretical keep-alive/LWT comparison; it is labeled as an estimate rather than an observed broker benchmark.
- Clarified in report documentation that seed histograms count trials, P95 is not a confidence interval, and missing telemetry does not establish physical thermal compliance.

### Free Wokwi-to-Node-RED integration

- Added a namespace-limited inbound Mosquitto bridge from the free Wokwi/HiveMQ path to the local Node-RED broker.
- Kept the local Mosquitto listener loopback-only and Node-RED on the Compose network.
- Assigned a project-specific device ID to reduce accidental collisions on the shared public broker.
- Saved the public Wokwi project at `https://wokwi.com/projects/481333516199647233`.
- Verified the HiveMQ-to-local-Mosquitto bridge with a synthetic test message. An earlier Wokwi Public Gateway attempt returned HTTP 503; the cause is unknown.
- Added serial diagnostics for Wi-Fi/MQTT connection attempts and configured Wokwi's documented Wi-Fi channel 6 to skip scanning.
- Added and ran a separate Wokwi network diagnostic sketch to distinguish virtual Wi-Fi association and outbound TCP reachability from MQTT and sensor behavior.
- Fixed the DHT22 data connection: the prior `esp:15` endpoint did not render/connect the SDA pin. The diagram now uses Wokwi's documented `wokwi-esp32-devkit-v1` part with `D15`/`D27` endpoints and the ESP32-specific DHT library. A sensor-only test repeatedly reads 5.00 C and 55.00% humidity.
- On 2026-11-21, a foreground Wokwi run using the Public Gateway connected to HiveMQ. A local Mosquitto subscriber captured three Wokwi-originated telemetry samples (5.00 C, 55.00% humidity, door closed; uptimes 92, 102, and 112 seconds), and the Node-RED dashboard displayed 5 C / 55% with the device online. After stopping the simulation, the retained status and dashboard showed offline; the exact LWT detection interval was not measured.
- During a follow-up session, three restart attempts stayed at `Connecting to Wi-Fi` for approximately 10, 15, and 15 seconds. They were stopped before further testing; no new telemetry was observed, and the cause was not established. The final simulator state was stopped.
- The signed-in Wokwi page displayed an upgrade prompt when **Enable Private Gateway** was selected, despite the user's report that Pro had been activated. The Private Gateway was therefore not used; the successful run used the existing public-broker bridge.

## Suggested maintenance workflow

1. Read this file, the relevant component `README.md`, and [`docs/architecture.md`](docs/architecture.md) before changing a topic or flow.
2. Keep the firmware payload, simulator row/event schema, Node-RED validation, docs, and tests consistent.
3. Add or adjust focused tests for any new simulation behavior.
4. Run `python -m simulation.run_simulation --seed 410103 --runs 5 --sensitivity-analysis` and `python -m unittest discover -s tests -v`.
5. Regenerate checked-in report snapshots only when intentionally updating the published example metrics.
6. Do not commit credentials or expose the anonymous demo broker.
