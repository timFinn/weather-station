# Home Assistant MQTT Discovery

## Overview

Add MQTT Discovery support so Home Assistant automatically creates sensor entities when the weather station connects to the broker. No manual `configuration.yaml` edits required for HA users.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target platform | Home Assistant only | De facto standard; requested by users (GitHub #1) |
| Default behavior | On, opt-out via `HA_DISCOVERY=false` | New users get autodiscovery immediately; advanced users can disable |
| Device grouping | Two devices: Weather Station + Pi System | Weather data and Pi health are separate concerns |
| Implementation | Separate `weatherhat/ha_discovery.py` module | Mirrors `i2c_recovery.py` pattern; keeps publisher focused |
| Payload compatibility | No changes to existing `send_payload` format | `value_template` in discovery config adapts to current `{topic: value}` format |

## Module: `weatherhat/ha_discovery.py`

### Sensor Definitions

Two dicts mapping sensor keys (matching existing `TOPICS` keys in mqtt-publisher.py) to HA metadata:

**`WEATHER_SENSORS`** — grouped under the Weather Station device:

| Key | Name | device_class | unit | state_class |
|-----|------|-------------|------|-------------|
| `temperature` | Temperature | `temperature` | `°C` | `measurement` |
| `humidity` | Humidity | `humidity` | `%` | `measurement` |
| `relative_humidity` | Relative Humidity | `humidity` | `%` | `measurement` |
| `pressure` | Pressure | `atmospheric_pressure` | `hPa` | `measurement` |
| `dewpoint` | Dew Point | `temperature` | `°C` | `measurement` |
| `light` | Light | `illuminance` | `lx` | `measurement` |
| `wind_speed` | Wind Speed | `wind_speed` | `m/s` | `measurement` |
| `wind_direction` | Wind Direction | _(none)_ | _(none)_ | _(none)_ |
| `rain` | Rain Rate | `precipitation_intensity` | `mm/s` | `measurement` |
| `rain_total` | Rain Total | `precipitation` | `mm` | `total_increasing` |

**`PI_SENSORS`** — grouped under the Pi System device:

| Key | Name | device_class | unit | state_class |
|-----|------|-------------|------|-------------|
| `cpu_temp` | CPU Temperature | `temperature` | `°C` | `measurement` |
| `throttled` | Throttle Status | _(none)_ | _(none)_ | _(none)_ |
| `undervoltage` | Undervoltage | _(none)_ | _(none)_ | _(none)_ |
| `undervoltage_now` | Undervoltage Now | _(none)_ | _(none)_ | _(none)_ |

Sensors without a `device_class` (wind_direction, throttled, undervoltage) use an `icon` instead for HA display:

| Key | Icon |
|-----|------|
| `wind_direction` | `mdi:windsock` |
| `throttled` | `mdi:gauge` |
| `undervoltage` | `mdi:flash-alert` |
| `undervoltage_now` | `mdi:flash-alert-outline` |

### Device Objects

Built dynamically from `MQTT_CLIENT_ID`:

**Weather Station:**
```json
{
  "identifiers": ["{client_id}"],
  "name": "Weather Station",
  "model": "Weather HAT",
  "manufacturer": "Pimoroni"
}
```

**Pi System:**
```json
{
  "identifiers": ["{client_id}-pi"],
  "name": "Weather Station Pi",
  "model": "Raspberry Pi",
  "manufacturer": "Raspberry Pi"
}
```

### Discovery Payloads

For each sensor, publish a retained config message to:
```
homeassistant/sensor/{client_id}_{sensor_key}/config
```

Payload structure (example for temperature):
```json
{
  "name": "Temperature",
  "device_class": "temperature",
  "unit_of_measurement": "\u00b0C",
  "state_class": "measurement",
  "state_topic": "sensors/weather/temperature",
  "value_template": "{{ value_json['sensors/weather/temperature'] }}",
  "unique_id": "weatherhat-garden_temperature",
  "device": {
    "identifiers": ["weatherhat-garden"],
    "name": "Weather Station",
    "model": "Weather HAT",
    "manufacturer": "Pimoroni"
  },
  "availability_topic": "sensors/weather/status",
  "payload_available": "online",
  "payload_not_available": "offline"
}
```

### Public API

```python
def publish_discovery_configs(client, topic_prefix, client_id):
    """Publish HA MQTT Discovery config for all sensors.

    Args:
        client: Connected paho MQTT client instance.
        topic_prefix: MQTT topic prefix (e.g., "sensors").
        client_id: MQTT client ID, used for unique_id and device identifier.
    """
```

Iterates both `WEATHER_SENSORS` and `PI_SENSORS`, builds the config payload for each, and publishes with `retain=True, qos=1`.

## Integration: `bin/mqtt-publisher.py`

### New Configuration

```python
HA_DISCOVERY = os.getenv("HA_DISCOVERY", "true").lower() != "false"
```

### on_connect Change

After publishing the "online" status, publish discovery configs if enabled:

```python
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT broker ...")
        client.publish(TOPICS['status'], payload="online", qos=1, retain=True)
        if HA_DISCOVERY:
            publish_discovery_configs(client, MQTT_TOPIC_PREFIX, MQTT_CLIENT_ID)
    ...
```

Discovery is published on every connect, not just the first. This handles HA restarts and broker restarts — retained messages ensure idempotency.

### No Changes To

- `send_payload()` — existing `{topic: value}` format is unchanged
- `TOPICS` dict — no new topics
- Existing sensor read/publish loop — untouched

## Configuration

Add `HA_DISCOVERY` to `config/mqtt.env.example`:

```bash
# Home Assistant MQTT Discovery (default: true, set to false to disable)
HA_DISCOVERY=true
```

Update `docs/MQTT.md` configuration table to include the new variable.

## Test Harness: `scripts/test-ha-discovery.py`

Standalone MQTT consumer that validates discovery payloads and data flow without requiring a Home Assistant installation.

### What It Does

1. Connects to the MQTT broker
2. Subscribes to `homeassistant/sensor/+/config`
3. Validates each discovery payload:
   - Required keys present (`name`, `state_topic`, `unique_id`, `device`, `value_template`)
   - `state_topic` matches expected prefix pattern
   - `availability_topic` is set
   - Both device identifiers appear (Weather Station + Pi System)
4. Subscribes to the `state_topic` from each discovered entity
5. Waits for a round of sensor data and verifies:
   - Payload is valid JSON
   - The key referenced by `value_template` exists in the payload
6. Reports summary: entities discovered, data received, any failures

### Usage

```bash
# Run against the Pi's MQTT broker after deploying
python3 scripts/test-ha-discovery.py --host mqtt.example.com --timeout 30
```

Exits 0 on success, non-zero with failure summary.

### Dependencies

`paho-mqtt` only (already a project dependency). No HA installation needed.

## Documentation Updates

- `docs/MQTT.md`: Add `HA_DISCOVERY` to configuration table, add section on autodiscovery
- `README.md`: Mention autodiscovery in features list
- `config/mqtt.env.example`: Add `HA_DISCOVERY` variable

## Delivery

- Implement on a local feature branch
- Validate with linting + test harness
- Deploy to Pi hardware for live validation
- Push branch to GitHub mirror
- PR against timFinn/weather-station#1
