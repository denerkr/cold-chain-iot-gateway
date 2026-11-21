# Mosquitto Configuration

`mosquitto.conf` starts an MQTT listener on port 1883, enables persistence in the Compose-managed data volume, and permits anonymous clients. Docker Compose publishes the port only on `127.0.0.1`, which keeps this teaching broker local to the computer.

The broker does not manufacture device status. The ESP32 sends retained `online` status and registers its own retained QoS 1 `offline` Last Will so a Node-RED container restart cannot impersonate a device outage.

## Start and verify

From the project root, run `docker compose up -d mosquitto`. The host port is `localhost:1883`; other Compose services reach it at `mosquitto:1883`. Anonymous access is for local experiments only. Add authentication and TLS before exposing any broker beyond loopback.

## Change history

- Initial prototype: created a persistent local MQTT 3.1.1 listener for the Compose stack.
- English documentation pass: documented loopback scope and clarified that device availability belongs to the ESP32 LWT.
