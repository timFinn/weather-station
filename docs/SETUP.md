# Weather Station Setup Guide

Complete guide for installing and running the Weather HAT weather station on a Raspberry Pi.

## Prerequisites

- Raspberry Pi with 40-pin GPIO header
- Pimoroni Weather HAT
- Raspberry Pi OS Bookworm or later
- Python 3.7+

### Enable Required Interfaces

```bash
# Enable I2C and SPI
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot
```

### Verify Hardware

After reboot, check sensors are detected:

```bash
i2cdetect -y 1
```

Expected addresses:
- `0x12` - IO Expander
- `0x29` - LTR559 (light sensor)
- `0x76` or `0x77` - BME280 (temp/humidity/pressure)

## Installation

### Automated Install (Recommended)

The install script handles everything: creates the `weather` service user, sets up the virtual environment, installs dependencies, and configures the systemd service.

```bash
# Clone the repository
git clone https://github.com/yourusername/weather-station.git
cd weather-station

# Run the installer (as root)
sudo ./scripts/install-service.sh
```

The installer will:
1. Create the `weather` user with appropriate hardware permissions
2. Copy the project to `/home/weather/weather-station/`
3. Create a Python virtual environment at `/home/weather/.virtualenvs/pimoroni/`
4. Install all dependencies
5. Create `config/mqtt.env` from template (prompts you to edit)
6. Install and enable the systemd service

### Manual Install

If you prefer manual control:

```bash
# 1. Create service user
sudo useradd --create-home --shell /bin/bash weather
sudo usermod -aG i2c,gpio,spi weather

# 2. Set up project
sudo mkdir -p /home/weather/weather-station
sudo cp -r . /home/weather/weather-station/
sudo chown -R weather:weather /home/weather/weather-station

# 3. Create virtual environment
sudo -u weather python3 -m venv --system-site-packages /home/weather/.virtualenvs/pimoroni
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/pip install -r /home/weather/weather-station/requirements.txt

# 4. Configure MQTT
sudo cp /home/weather/weather-station/config/mqtt.env.example /home/weather/weather-station/config/mqtt.env
sudo chmod 600 /home/weather/weather-station/config/mqtt.env
sudo chown weather:weather /home/weather/weather-station/config/mqtt.env
sudo nano /home/weather/weather-station/config/mqtt.env

# 5. Install service
sudo cp /home/weather/weather-station/weatherhat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable weatherhat
sudo systemctl start weatherhat
```

## Configuration

Edit `/home/weather/weather-station/config/mqtt.env`:

```bash
# MQTT Broker Settings
MQTT_SERVER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password

# Client Settings (client ID must be unique across all MQTT clients)
MQTT_CLIENT_ID=weatherhat-pi
MQTT_TOPIC_PREFIX=sensors

# Sensor Settings
TEMP_OFFSET=-7.5          # Temperature compensation (adjust for your Pi)
UPDATE_INTERVAL=2.0       # Sensor read interval (seconds)
PUBLISH_INTERVAL=2.0      # MQTT publish interval (seconds)
```

After editing:
```bash
sudo systemctl restart weatherhat
```

## Service Management

### Basic Commands

```bash
# Check status
sudo systemctl status weatherhat

# Start/stop/restart
sudo systemctl start weatherhat
sudo systemctl stop weatherhat
sudo systemctl restart weatherhat

# Enable/disable auto-start
sudo systemctl enable weatherhat
sudo systemctl disable weatherhat
```

### Viewing Logs

```bash
# Live logs
sudo journalctl -u weatherhat -f

# Recent logs
sudo journalctl -u weatherhat -n 100

# Errors only
sudo journalctl -u weatherhat -p err
```

### Running Manually

For debugging, run the publisher directly:

```bash
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/mqtt-publisher.py
```

## Updating

Pull the latest code and restart the service:

```bash
sudo ./scripts/update.sh
```

This will:
1. Pull latest changes from git
2. Sync files to the deployment directory (preserving `config/mqtt.env`)
3. Update pip dependencies if `requirements.txt` changed
4. Reload the systemd unit file if it changed
5. Restart the service

## Display Service (Optional)

Install the LCD display interface to show weather data locally:

```bash
sudo ./scripts/install-display-service.sh
```

This runs alongside the MQTT publisher. See [DISPLAY.md](DISPLAY.md) for details.

## Verifying Data Flow

### Check MQTT Messages

From another machine with mosquitto-clients:

```bash
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v
```

Expected output:
```
sensors/weather/temperature {"value": 23.4, "timestamp": 1704067200.123}
sensors/weather/humidity {"value": 45.2, "timestamp": 1704067200.234}
sensors/weather/pressure {"value": 1013.2, "timestamp": 1704067200.345}
...
```

## Troubleshooting

### Service Won't Start

```bash
# Check detailed error
sudo journalctl -u weatherhat -n 50 --no-pager

# Verify paths exist
ls -la /home/weather/weather-station/bin/mqtt-publisher.py
ls -la /home/weather/weather-station/config/mqtt.env

# Test manually
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/mqtt-publisher.py
```

### I2C/Sensor Errors

```bash
# Check I2C is enabled
i2cdetect -y 1

# Check user has permissions
groups weather  # Should include: i2c gpio spi

# Re-enable interfaces if needed
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot
```

### MQTT Connection Fails

```bash
# Run the diagnostic script
sudo ./scripts/test-mqtt.sh

# Test broker connectivity
ping YOUR_MQTT_SERVER

# Test MQTT with mosquitto
mosquitto_pub -h YOUR_MQTT_SERVER -p 1883 -t test -m "hello"

# Check credentials in config
sudo cat /home/weather/weather-station/config/mqtt.env | grep MQTT
```

### MQTT Reconnect Loop

If logs show repeated connect/disconnect cycles, the client ID is likely in use by another MQTT client (e.g. Telegraf). Set a unique `MQTT_CLIENT_ID` in `config/mqtt.env` and restart the service.

### GPIO Busy Errors

```bash
# Find processes using GPIO
sudo lsof /dev/gpiochip*
ps aux | grep -E "mqtt|weather"

# Kill stuck processes
sudo pkill -f mqtt-publisher.py
```

### High CPU Usage

The publisher should use <1% CPU. If higher:

```bash
# Check actual usage
top -p $(pgrep -f mqtt-publisher.py)

# Check logs for rapid error loops
sudo journalctl -u weatherhat -n 100 | grep -i error
```

## File Locations

```
/home/weather/weather-station/
├── bin/
│   ├── mqtt-publisher.py      # MQTT publisher script
│   └── display-interface.py   # Display interface script
├── config/
│   ├── mqtt.env.example       # Configuration template
│   └── mqtt.env               # Your configuration (create this)
├── weatherhat/                # Core sensor library
├── scripts/
│   ├── install-service.sh     # Main installer
│   ├── install-display-service.sh
│   ├── update.sh              # Pull latest and restart service
│   └── test-mqtt.sh           # MQTT diagnostic tests
├── weatherhat.service         # Systemd service definition
└── weatherhat-display.service # Display service definition

/etc/systemd/system/
├── weatherhat.service         # Installed service file
└── weatherhat-display.service # Installed display service
```

## Performance

Expected resource usage:
- **CPU**: <1% average
- **Memory**: 30-50 MB
- **MQTT messages**: Every 2 seconds (configurable)

## Security Notes

1. **Protect credentials**: `chmod 600` on mqtt.env
2. **Don't commit secrets**: mqtt.env is in .gitignore
3. **Use MQTT authentication**: Set username/password in config
4. **Service user isolation**: Runs as dedicated `weather` user
