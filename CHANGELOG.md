# Changelog

## 2026-02-28

### Fixed
- Fixed MQTT reconnect spin loop that caused service interruption after days of uptime
- Removed manual `reconnect()` call that raced with paho's internal network loop, causing the broker to see duplicate connections from the same client ID
- Backoff delay now applies unconditionally and only resets after a stable connection

### Added
- `scripts/update.sh` - Pull latest code and restart the service, preserving `config/mqtt.env`
- `scripts/test-mqtt.sh` - MQTT diagnostic script (DNS, TCP, auth, client ID conflicts, round-trip, broker stats, service status, data flow)
- Default `MQTT_CLIENT_ID` now includes hostname (`weatherhat-{hostname}`) to avoid client ID collisions

## Local fork
Modified for local MQTT publishing to Mosquitto broker.
