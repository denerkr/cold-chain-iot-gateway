# Development Notes and Change History

This file records the design intent and development context needed to continue the project without reconstructing decisions from code alone. Detailed component call paths are in [`docs/architecture.md`](docs/architecture.md); each component directory also has a `README.md`.

## Design decisions

- **MQTT topic contract:** `cold-chain/<device_id>/telemetry`, `cold-chain/<device_id>/alarms`, and `cold-chain/<device_id>/status` separate measurements, events, and availability. Keep `device_id` stable and unique per simulated node.
- **Alarm range and cadence:** temperature compliance is 2-8 C; telemetry is published every 10 seconds; door alarms begin after 30 seconds. Backend door timing is based on telemetry arrival, so detection occurs on the first sample after the threshold rather than at an exact 30-second instant.
- **Last Will:** the ESP32, not Node-RED, owns its retained QoS 1 `offline` will. The broker's detection interval depends on its keep-alive handling; 1.5 times 30 seconds is an estimate, not a measured guarantee.
- **Two rule evaluators:** firmware reports local alarms and Node-RED independently evaluates telemetry. Backend alarms are routed directly to the dashboard rather than republished to MQTT, avoiding a publish/subscribe feedback loop. Device-originated alarms remain available on the MQTT alarm topic.
- **Broker separation:** the Compose stack supplies a loopback-only local Mosquitto broker. The Wokwi sketch defaults to a public HiveMQ broker because a hosted simulator cannot resolve the Compose-only `mosquitto` name. For live integration, configure both clients to use the same reachable broker; keep the public broker limited to non-sensitive demonstrations.
- **Offline model:** the Python simulator intentionally needs no broker, Docker, Wokwi, or hardware. Synthetic network, alarm, and LWT metrics are explicitly labeled as simulated and must not be presented as measurements.
- **Monte Carlo runs:** `--runs N` evaluates sequential independent seeds `base_seed` through `base_seed + N - 1`. Aggregates include the individual values, mean, sample deviation, and a normal-approximation 95% interval. A single seed cannot estimate an interval.
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

## Suggested maintenance workflow

1. Read this file, the relevant component `README.md`, and [`docs/architecture.md`](docs/architecture.md) before changing a topic or flow.
2. Keep the firmware payload, simulator row/event schema, Node-RED validation, docs, and tests consistent.
3. Add or adjust focused tests for any new simulation behavior.
4. Run `python -m simulation.run_simulation --seed 410103 --runs 5` and `python -m unittest discover -s tests -v`.
5. Regenerate checked-in report snapshots only when intentionally updating the published example metrics.
6. Do not commit credentials or expose the anonymous demo broker.
