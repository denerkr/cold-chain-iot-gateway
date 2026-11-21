# Wokwi ESP32 Device

This directory contains the simulated board wiring (`diagram.json`), firmware (`sketch.ino`), and required Arduino libraries (`libraries.txt`). The ESP32 uses GPIO 15 for the DHT22 data line and GPIO 27 for the door push button; the button is read with `INPUT_PULLUP`.

## Wokwi setup

1. Create an ESP32 project at `https://wokwi.com/projects/new/esp32`.
2. Copy `sketch.ino` and `diagram.json` into the project.
3. Install each library listed in `libraries.txt`.
4. Run the simulation, adjust the DHT22 temperature or humidity, and press `D` to open or close the door.

The default sketch connects to `broker.hivemq.com:1883` with no TLS or authentication. Configure the Node-RED MQTT broker to use the same reachable broker for a hosted end-to-end demo. The public broker is not suitable for sensitive data. The local Compose `mosquitto` hostname is unavailable to Wokwi.

## Firmware function map

- `topic`: build the device's topic path.
- `connectWifi`: join the simulator Wi-Fi network.
- `connectMqtt`: configure keep-alive and the retained offline will, then publish the retained online status.
- `publishAlarm`: encode and send a structured alarm event.
- `publishTelemetry`: read both sensors, track state transitions, and publish the JSON sample.
- `setup`: initialize the serial console, pin, sensor, Wi-Fi, and MQTT client.
- `loop`: maintain connectivity and call the telemetry publisher every 10 seconds.

See [`../docs/architecture.md`](../docs/architecture.md) for the call graph and MQTT payload contract.

## Change history

- Initial prototype: added DHT22 and door wiring, 10-second telemetry, thermal/door alarms, and retained MQTT LWT status.
- English documentation pass: translated serial errors, alarm messages, simulator labels, and code comments.
