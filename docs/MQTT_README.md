# WeatherHAT MQTT Publisher - Improved Version

This is an improved, production-ready version of the MQTT weather station publisher with enhanced security, reliability, and error handling.

## Key Improvements

### Security
- ✅ **No hardcoded credentials** - Uses environment variables
- ✅ **Removed unsafe subprocess calls** - No more `sudo ifconfig` commands
- ✅ **Support for MQTT authentication** - Username/password support
- ✅ **Proper logging** - Structured logging instead of print statements

### Reliability
- ✅ **Exponential backoff** - Smart reconnection with increasing delays (1s → 5min max)
- ✅ **Graceful shutdown** - Handles SIGINT/SIGTERM properly
- ✅ **Better error handling** - Specific exceptions with proper recovery
- ✅ **QoS 1 publishing** - Ensures message delivery

### Performance
- ✅ **Efficient sensor reading** - Structured data handling
- ✅ **Configurable intervals** - Separate update and publish intervals
- ✅ **Reduced CPU usage** - Removed unnecessary operations

## Configuration

### Using Environment Variables (Recommended)

1. Copy the example environment file:
```bash
cd ~/weatherhat-python/examples
cp mqtt.env.example mqtt.env
```

2. Edit `mqtt.env` with your settings:
```bash
nano mqtt.env
```

3. Run with environment variables (choose one method):

**Method 1: Using the helper script (easiest)**
```bash
./run-mqtt.sh
```

**Method 2: Using source (recommended for manual runs)**
```bash
set -a
source mqtt.env
set +a
python3 mqtt.py
```

**Method 3: One-liner (for testing)**
```bash
env $(grep -v '^#' mqtt.env | xargs) python3 mqtt.py
```

### Using a systemd Service

Create `/etc/systemd/system/weatherhat-mqtt.service`:

```ini
[Unit]
Description=WeatherHAT MQTT Publisher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Pimoroni/weatherhat/examples
EnvironmentFile=/home/pi/Pimoroni/weatherhat/examples/mqtt.env
ExecStart=/home/pi/.virtualenvs/pimoroni/bin/python3 /home/pi/Pimoroni/weatherhat/examples/mqtt.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable weatherhat-mqtt.service
sudo systemctl start weatherhat-mqtt.service
```

Check status:
```bash
sudo systemctl status weatherhat-mqtt.service
sudo journalctl -u weatherhat-mqtt.service -f
```

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
```

## Payload Format

Each message contains JSON with value and timestamp:

```json
{
  "value": 23.5,
  "timestamp": 1704067200.123
}
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_SERVER` | `localhost` | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | _(empty)_ | MQTT username (optional) |
| `MQTT_PASSWORD` | _(empty)_ | MQTT password (optional) |
| `MQTT_CLIENT_ID` | `weatherhat` | Unique client identifier |
| `MQTT_TOPIC_PREFIX` | `sensors` | Topic prefix for all messages |
| `TEMP_OFFSET` | `-7.5` | Temperature compensation offset (°C) |
| `UPDATE_INTERVAL` | `2.0` | Sensor update interval (seconds) |
| `PUBLISH_INTERVAL` | `2.0` | MQTT publish interval (seconds) |

## Troubleshooting

### Connection Issues

Check logs:
```bash
# If running manually
python3 mqtt.py

# If running as service
sudo journalctl -u weatherhat-mqtt.service -n 50
```

Test MQTT connection:
```bash
mosquitto_pub -h mqtt.example.com -p 1883 -t test -m "hello"
```

### Sensor Errors

Check I2C is enabled:
```bash
sudo raspi-config nonint do_i2c 0
```

Test I2C devices:
```bash
i2cdetect -y 1
```

### Permission Issues

If you get I2C permission errors, add user to i2c group:
```bash
sudo usermod -a -G i2c,gpio $USER
# Log out and back in
```

## Differences from Original

| Feature | Original | Improved |
|---------|----------|----------|
| Configuration | Hardcoded | Environment variables |
| Logging | `print()` statements | Structured logging |
| Error handling | Broad `except Exception` | Specific exceptions |
| Reconnection | Fixed 5s delay | Exponential backoff (1-300s) |
| Shutdown | Abrupt | Graceful with cleanup |
| Network recovery | `subprocess` sudo calls | Removed (not needed) |
| MQTT QoS | 0 (fire and forget) | 1 (at least once) |
| Payload format | `{topic: value}` | `{value: X, timestamp: T}` |

## Security Notes

1. **Never commit `mqtt.env`** - It contains credentials
2. Add to `.gitignore`:
   ```bash
   echo "mqtt.env" >> .gitignore
   ```
3. For production, consider using TLS:
   ```python
   mqtt_client.tls_set(ca_certs="/path/to/ca.crt")
   ```
4. Use strong MQTT passwords and restrict broker access

## Migration from Original

To migrate from the original mqtt.py:

1. Backup your current script
2. Replace with new version
3. Create `mqtt.env` with your settings
4. Update any hardcoded values (server, offsets, etc.)
5. Test before deploying to production
6. Set up systemd service for auto-start

## Support

- Report issues: https://github.com/pimoroni/weatherhat-python/issues
- Documentation: https://github.com/pimoroni/weatherhat-python
