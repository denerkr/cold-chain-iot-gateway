# Project Documentation

`architecture.md` is the cross-component reference: it diagrams the message sequence, ESP32 function call graph, Node-RED routing, simulator call path, and MQTT payload contract. It is the best starting point when tracing a sensor reading or alarm across the whole system.

The root `DEVELOPMENT.md` records design choices and the chronological change history. Each implementation directory also documents its local responsibilities and changes.

## Change history

- Initial prototype: documented component boundaries and MQTT topic ownership.
- English documentation pass: added call-path diagrams and a cross-component change checklist for maintainers.
