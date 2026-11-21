# Node-RED Flows

`flows.json` contains the Node-RED workspace tab, MQTT broker reference, subscriptions, validation and alarm function nodes, Dashboard gauges/charts/text widgets, and dashboard tab/group. `package.json` installs the legacy `node-red-dashboard` package used by the flow.

## Startup and broker configuration

Docker Compose mounts this directory at `/data` and sets `FLOWS=flows.json`. Start the stack with `docker compose up -d`, edit flows at `http://localhost:1880`, and view the dashboard at `http://localhost:1880/ui`.

The default broker host is `mosquitto`, which is the Docker Compose service name. It is not reachable directly from Wokwi. For a live hosted-simulator demonstration, edit the MQTT broker configuration in the Node-RED editor so it points to the same broker host and port used by the sketch. Do not use a public demo broker for sensitive data.

## Flow responsibilities

- Telemetry input subscribes to `cold-chain/+/telemetry`.
- `validate-and-route` parses and validates JSON, updates dashboard widgets, applies per-device thermal/door rules, and forwards local alarms directly to the formatter.
- Alarm input subscribes to firmware events on `cold-chain/+/alarms`.
- `format-alarm` validates an alarm object and displays the latest event.
- Status input subscribes to retained `cold-chain/+/status` and displays the publisher status.

Backend-generated alerts are deliberately not republished through MQTT; direct routing avoids a broker echo loop. Device-generated alerts remain on MQTT. Both rule evaluators can independently report the same physical condition.

## Change history

- Initial prototype: added MQTT broker, dashboard widgets, sensor checks, and MQTT alarm subscriptions.
- English documentation pass: translated dashboard and validation messages.
- Reliability correction: removed Node-RED's birth/close/will publications from the ESP32 status topic; only the ESP32 should report its own liveness.
- Reliability correction: routed local rule alarms straight to the dashboard and preserve simultaneous thermal and door alerts.
