# Weather HAT Quick Start Guide

## Fresh Installation

### 1. Install Dependencies
```bash
cd ~/weatherhat-python/scripts
./install-dependencies.sh
```

### 2. Configure MQTT
```bash
cd ~/weatherhat-python/examples
cp mqtt.env.example mqtt.env
nano mqtt.env
```

Edit these required settings:
- `MQTT_SERVER=your.mqtt.server`
- `MQTT_PORT=1883` (or your port)
- `MQTT_USERNAME=` (if needed)
- `MQTT_PASSWORD=` (if needed)
- `TEMP_OFFSET=-7.5` (adjust for your Pi)

### 3. Test Manually
```bash
cd ~/weatherhat-python/examples
source ~/.virtualenvs/pimoroni/bin/activate
./run-mqtt.sh
```

Watch for:
- "Connected to MQTT broker" message
- No errors
- Data flowing (check with `mosquitto_sub`)

### 4. Install Service (for auto-start)
```bash
cd ~/weatherhat-python/scripts
sudo ./install-service.sh
```

Follow the prompts to:
- Create/configure mqtt.env
- Remove old cron jobs
- Install and start the service

### 5. Verify Service
```bash
# Check status
sudo systemctl status weatherhat

# Watch live logs
sudo journalctl -u weatherhat -f

# Check CPU usage (should be <1%)
top -p $(pgrep -f mqtt.py)
```

---

## Common Commands

### Manual Testing
```bash
cd ~/weatherhat-python/examples
source ~/.virtualenvs/pimoroni/bin/activate
./run-mqtt.sh
```

### Service Management
```bash
# Start/Stop/Restart
sudo systemctl start weatherhat
sudo systemctl stop weatherhat
sudo systemctl restart weatherhat

# Check status
sudo systemctl status weatherhat

# View logs
sudo journalctl -u weatherhat -f          # Live
sudo journalctl -u weatherhat -n 100      # Last 100 lines
sudo journalctl -u weatherhat -p err      # Errors only
```

### Configuration Changes
```bash
# Edit settings
nano ~/weatherhat-python/examples/mqtt.env

# Restart to apply
sudo systemctl restart weatherhat
```

### Monitoring
```bash
# CPU/Memory usage
top -p $(pgrep -f mqtt.py)

# Subscribe to MQTT topics
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v
```

---

## Troubleshooting

### mqtt.py won't start
```bash
# Check environment file
cat ~/weatherhat-python/examples/mqtt.env

# Test with verbose logging
cd ~/weatherhat-python/examples
source ~/.virtualenvs/pimoroni/bin/activate
python3 -c "import logging; logging.basicConfig(level='DEBUG'); import mqtt"
```

### I2C errors
```bash
# Check I2C devices
i2cdetect -y 1

# Expected addresses:
# 0x12 - IO Expander
# 0x29 - LTR559 (light sensor)
# 0x76 or 0x77 - BME280 (temp/humidity/pressure)

# Enable I2C if needed
sudo raspi-config nonint do_i2c 0
sudo reboot
```

### MQTT connection fails
```bash
# Test MQTT broker connectivity
ping YOUR_MQTT_SERVER

# Test MQTT with mosquitto
mosquitto_pub -h YOUR_MQTT_SERVER -p 1883 -t test -m "hello"

# Check credentials
grep MQTT ~/weatherhat-python/examples/mqtt.env
```

### Service won't start
```bash
# Check service file
sudo systemctl cat weatherhat

# Check journal for errors
sudo journalctl -u weatherhat -n 50

# Verify paths exist
ls -la ~/weatherhat-python/examples/mqtt.py
ls -la ~/weatherhat-python/examples/mqtt.env
```

### High CPU usage
```bash
# Should be <1%, if higher:
top -p $(pgrep -f mqtt.py)

# Check version (improved version uses ~0.01% CPU)
grep "MQTT Weather Station Publisher" ~/weatherhat-python/examples/mqtt.py
```

---

## File Locations

```
~/weatherhat-python/
├── examples/
│   ├── mqtt.py                 # Main script (improved)
│   ├── mqtt.env                # Your configuration (create from .example)
│   ├── mqtt.env.example        # Template
│   ├── run-mqtt.sh             # Helper script
│   └── MQTT_README.md          # Full documentation
├── scripts/
│   ├── install-dependencies.sh # Install Python packages
│   └── install-service.sh      # Install systemd service
├── weatherhat/
│   ├── __init__.py             # Core library (optimized)
│   └── history.py              # Data history (optimized)
├── weatherhat.service          # systemd service definition
└── IMPROVEMENTS_SUMMARY.md     # Technical details
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_SERVER` | `localhost` | **Required** - MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | _(empty)_ | Username (if authentication required) |
| `MQTT_PASSWORD` | _(empty)_ | Password (if authentication required) |
| `MQTT_CLIENT_ID` | `weatherhat` | Unique client identifier |
| `MQTT_TOPIC_PREFIX` | `sensors` | Topic prefix for all messages |
| `TEMP_OFFSET` | `-7.5` | Temperature compensation (adjust for your Pi) |
| `UPDATE_INTERVAL` | `2.0` | Sensor reading interval (seconds) |
| `PUBLISH_INTERVAL` | `2.0` | MQTT publish interval (seconds) |

---

## Performance Expectations

After improvements:
- **CPU usage**: <1% average (down from ~2-3%)
- **Memory**: ~30-50MB
- **MQTT messages**: Every 2 seconds (configurable)
- **Reconnection**: Automatic with exponential backoff

---

## Getting Help

1. **Check logs first**: `sudo journalctl -u weatherhat -n 100`
2. **Test manually**: `./run-mqtt.sh` to see errors directly
3. **Verify hardware**: `i2cdetect -y 1`
4. **Check documentation**: See `examples/MQTT_README.md`
5. **Review improvements**: See `IMPROVEMENTS_SUMMARY.md`

---

## Upgrade from Old Version

If upgrading from original mqtt.py:

1. **Backup old configuration**:
   ```bash
   cp ~/weatherhat-python/examples/mqtt.py ~/weatherhat-python/examples/mqtt.py.old
   ```

2. **Stop old service**:
   ```bash
   sudo systemctl stop weatherhat
   # or kill old process
   ```

3. **Create mqtt.env**:
   ```bash
   cd ~/weatherhat-python/examples
   cp mqtt.env.example mqtt.env
   nano mqtt.env  # Add your old settings
   ```

4. **Test new version**:
   ```bash
   ./run-mqtt.sh
   ```

5. **Update service**:
   ```bash
   cd ~/weatherhat-python/scripts
   sudo ./install-service.sh
   ```

See `MIGRATION_CHECKLIST.md` for complete migration guide.
