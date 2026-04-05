# Weather Station

A Python weather station for Raspberry Pi using the Pimoroni Weather HAT. Reads temperature, humidity, pressure, light, wind, and rain data, then publishes to MQTT for home automation and monitoring.

## Features

- **MQTT Publishing** - Sends weather and system data to any MQTT broker with QoS 1
- **Resilient Operation** - Automatic I2C bus recovery, sensor timeout protection, and graduated error handling with diagnostic logging
- **Online/Offline Status** - MQTT Last Will and Testament (LWT) for real-time availability monitoring
- **System Monitoring** - Publishes Pi CPU temperature, throttle state, and undervoltage detection
- **Home Assistant Discovery** - Automatic entity creation via MQTT Discovery (opt-out with `HA_DISCOVERY=false`)
- **LCD Display** - Shows live data and historical graphs on the Weather HAT screen
- **Power Efficient** - Display sleeps when not in use
- **Container Support** - Run via Podman for easy deployment
- **Systemd Services** - Auto-start on boot with proper logging
- **Diagnostics** - Built-in MQTT connectivity tests and system optimization audits

## Quick Start

### Prerequisites

- Raspberry Pi with 40-pin GPIO
- Pimoroni Weather HAT
- I2C and SPI enabled (`sudo raspi-config`)

### Install

```bash
git clone https://github.com/timFinn/weather-station.git
cd weather-station
sudo ./scripts/install-service.sh
```

The installer creates a `weather` service user, sets up the Python environment, and configures the systemd service. You'll be prompted to configure your MQTT broker settings.

### Verify

```bash
# Check service status
sudo systemctl status weatherhat

# Run MQTT diagnostics
sudo ./scripts/test-mqtt.sh

# View logs
sudo journalctl -u weatherhat -f

# Subscribe to MQTT topics (from another machine)
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v
```

### Update

```bash
sudo ./scripts/update.sh
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Setup Guide](docs/SETUP.md) | Full installation and configuration |
| [MQTT Publisher](docs/MQTT.md) | MQTT topics, payload format, integration |
| [Display Interface](docs/DISPLAY.md) | LCD screen controls and customization |
| [Container Deployment](docs/CONTAINER.md) | Running with Podman |

## Project Structure

```
weather-station/
├── bin/                    # Production scripts
│   ├── mqtt-publisher.py   # MQTT publisher
│   └── display-interface.py # LCD display interface
├── config/                 # Configuration
│   ├── mqtt.env.example    # Template
│   └── mqtt.env            # Your settings (create this)
├── weatherhat/             # Sensor library
├── scripts/                # Installation, update, and diagnostic scripts
├── docs/                   # Documentation
├── examples/               # Example scripts
├── Containerfile           # Container build
└── .forgejo/workflows/     # CI/CD
```

## Configuration

Edit `config/mqtt.env`:

```bash
MQTT_SERVER=mqtt.example.com
MQTT_PORT=1883
MQTT_USERNAME=weatherhat
MQTT_PASSWORD=<your-password>
TEMP_OFFSET=-7.5
```

See [MQTT.md](docs/MQTT.md) for all options.

## MQTT Topics

### Weather Sensors
```
sensors/weather/temperature      - Compensated air temperature (°C)
sensors/weather/humidity         - Raw humidity (%)
sensors/weather/relative_humidity - Relative humidity (%)
sensors/weather/pressure         - Atmospheric pressure (hPa)
sensors/weather/dewpoint         - Dew point (°C)
sensors/weather/light            - Light level (lux)
sensors/weather/wind_speed       - Wind speed (m/s)
sensors/weather/wind_direction   - Wind direction (cardinal)
sensors/weather/rain             - Rain rate (mm/s)
sensors/weather/rain_total       - Total rain in interval (mm)
sensors/weather/status           - Online/offline (retained, via LWT)
```

### System Monitoring
```
sensors/pi/cpu_temp              - CPU temperature (°C)
sensors/pi/throttled             - Throttle status (raw hex)
sensors/pi/undervoltage          - Undervoltage since boot (bool)
sensors/pi/undervoltage_now      - Undervoltage right now (bool)
```

## Container Deployment

```bash
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  weatherhat:latest
```

See [CONTAINER.md](docs/CONTAINER.md) for service setup and CI/CD details.

## Hardware

Based on the [Pimoroni Weather HAT](https://shop.pimoroni.com/products/weather-hat):

- BME280 - Temperature, humidity, pressure
- LTR559 - Light sensor
- IO Expander - Wind/rain sensor inputs
- ST7789 - 1.54" LCD display
- 4 buttons for display navigation

## License

MIT License - See [LICENSE](LICENSE) for details.
