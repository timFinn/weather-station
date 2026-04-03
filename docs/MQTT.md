# MQTT Publisher

The MQTT publisher reads sensor data from the Weather HAT and publishes it to an MQTT broker for consumption by home automation systems, databases, or other services.

## Features

- **Environment-based configuration** - No hardcoded credentials
- **Automatic reconnection** - Paho network loop handles recovery with exponential backoff (1s to 5min max)
- **Graceful shutdown** - Handles SIGINT/SIGTERM properly
- **QoS 1 publishing** - Ensures message delivery
- **Structured logging** - Easy debugging via journald
- **LWT status topic** - Broker publishes offline status on unexpected disconnect
- **Sensor error diagnostics** - Logs power state, I2C bus scan, and timing on failures
- **I2C bus recovery** - Automatic recovery via pinctrl bit-bang + driver rebind
- **Initialization timeout** - Prevents hung startup on stuck I2C bus

## MQTT Topics

Data is published to the following topics (prefix is configurable):

```
sensors/pi/cpu_temp              - CPU temperature (°C)
sensors/weather/temperature      - Compensated air temperature (°C)
sensors/weather/humidity         - Raw humidity (%)
sensors/weather/relative_humidity - Relative humidity (%)
sensors/weather/pressure         - Atmospheric pressure (hPa)
sensors/weather/dewpoint         - Dew point (°C)
sensors/weather/light            - Light level (lux)
sensors/weather/wind_direction   - Wind direction (cardinal)
sensors/weather/wind_speed       - Wind speed (m/s)
sensors/weather/rain             - Rain rate (mm/s)
sensors/weather/rain_total       - Total rain in interval (mm)
sensors/pi/throttled             - Pi throttle status (raw hex int)
sensors/pi/undervoltage          - Undervoltage since boot (bool)
sensors/pi/undervoltage_now      - Undervoltage right now (bool)
sensors/weather/status           - Online/offline (retained, set via LWT)
```

## Payload Format

Each message contains JSON with value and timestamp:

```json
{
  "value": 23.5,
  "timestamp": 1704067200.123
}
```

## Configuration

All settings are configured via environment variables in `config/mqtt.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_SERVER` | `localhost` | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | _(empty)_ | MQTT username (optional) |
| `MQTT_PASSWORD` | _(empty)_ | MQTT password (optional) |
| `MQTT_CLIENT_ID` | `weatherhat-{hostname}` | Unique client identifier |
| `MQTT_TOPIC_PREFIX` | `sensors` | Topic prefix for all messages |
| `TEMP_OFFSET` | `-7.5` | Temperature compensation offset (°C) |
| `UPDATE_INTERVAL` | `2.0` | Sensor update interval (seconds) |
| `PUBLISH_INTERVAL` | `5.0` | MQTT publish interval (seconds) |

### Example Configuration

```bash
# /home/weather/weather-station/config/mqtt.env

MQTT_SERVER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=weatherhat
MQTT_PASSWORD=secret123
MQTT_CLIENT_ID=weatherhat-garden
MQTT_TOPIC_PREFIX=sensors

TEMP_OFFSET=-7.5
UPDATE_INTERVAL=2.0
PUBLISH_INTERVAL=5.0
```

## Running

### As a Service (Recommended)

```bash
# Check status
sudo systemctl status weatherhat

# View logs
sudo journalctl -u weatherhat -f

# Restart after config changes
sudo systemctl restart weatherhat
```

### Manually

```bash
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/mqtt-publisher.py
```

## Verifying Data

Subscribe to the topics from another machine:

```bash
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v
```

Expected output:
```
sensors/weather/temperature {"value": 23.4, "timestamp": 1704067200.123}
sensors/weather/humidity {"value": 45.2, "timestamp": 1704067200.234}
sensors/weather/pressure {"value": 1013.2, "timestamp": 1704067200.345}
sensors/weather/dewpoint {"value": 11.2, "timestamp": 1704067200.456}
sensors/weather/light {"value": 1234, "timestamp": 1704067200.567}
sensors/weather/wind_direction {"value": "NE", "timestamp": 1704067200.678}
sensors/weather/wind_speed {"value": 1.2, "timestamp": 1704067200.789}
sensors/weather/rain {"value": 0.0, "timestamp": 1704067200.890}
sensors/pi/cpu_temp {"value": 45.6, "timestamp": 1704067200.901}
```

## Integration Examples

### InfluxDB via Telegraf

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mqtt.example.com:1883"]
  topics = ["sensors/#"]
  data_format = "json"
  json_time_key = "timestamp"
  json_time_format = "unix"
```

### Home Assistant

```yaml
mqtt:
  sensor:
    - name: "Weather Temperature"
      state_topic: "sensors/weather/temperature"
      value_template: "{{ value_json.value }}"
      unit_of_measurement: "°C"

    - name: "Weather Humidity"
      state_topic: "sensors/weather/humidity"
      value_template: "{{ value_json.value }}"
      unit_of_measurement: "%"
```

## Troubleshooting

### Run Diagnostics

The diagnostic script tests connectivity, authentication, client ID conflicts, round-trip publishing, and data flow:

```bash
sudo ./scripts/test-mqtt.sh
```

### Connection Issues

```bash
# Check logs
sudo journalctl -u weatherhat -n 50

# Test MQTT broker
mosquitto_pub -h YOUR_MQTT_SERVER -p 1883 -t test -m "hello"

# Verify credentials
sudo cat /home/weather/weather-station/config/mqtt.env | grep MQTT
```

### Client ID Conflicts

If the service connects then immediately disconnects in a loop, another MQTT client (e.g. Telegraf) may be using the same client ID. The broker only allows one connection per client ID — duplicates cause both clients to fight over the connection.

```bash
# Check for conflicts (holds the configured client ID for 5s)
sudo ./scripts/test-mqtt.sh  # See Test 4 output

# Fix by setting a unique client ID
sudo nano /home/weather/weather-station/config/mqtt.env
# Change MQTT_CLIENT_ID to something unique, e.g. weatherhat-pi
sudo systemctl restart weatherhat
```

### Sensor Errors

The publisher logs detailed diagnostics on sensor failures, including power state (undervoltage), I2C bus scan, service uptime, and time since last successful publish. Check the journal for `--- Sensor error diagnostics ---` blocks.

The error recovery sequence is:
1. **1-2 consecutive errors**: Log diagnostics, retry
2. **3 consecutive errors**: Attempt I2C bus recovery (pinctrl bit-bang + driver rebind), reinitialize sensors
3. **5 consecutive errors**: Exit for systemd restart

```bash
# Check I2C devices
i2cdetect -y 1

# Verify user permissions
groups weather  # Should include: i2c gpio spi

# Check for undervoltage (common cause of I2C failures)
vcgencmd get_throttled
```

### No Data Publishing

```bash
# Check service status topic (retained — shows last known state)
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/weather/status' -C 1

# Run manually to see errors
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/mqtt-publisher.py
```

## Security Notes

1. **Protect credentials**: Keep `mqtt.env` with `chmod 600`
2. **Don't commit secrets**: `mqtt.env` is in `.gitignore`
3. **Use authentication**: Always set MQTT username/password
4. **Consider TLS**: For production, use MQTT over TLS (port 8883)
