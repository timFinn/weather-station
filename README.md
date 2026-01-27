# Weather Station

A Python weather station for Raspberry Pi using the Pimoroni Weather HAT. Reads temperature, humidity, pressure, light, wind, and rain data, then publishes to MQTT for home automation and monitoring.

## Features

- **MQTT Publishing** - Sends sensor data to any MQTT broker
- **LCD Display** - Shows live data and historical graphs on the Weather HAT screen
- **Power Efficient** - Display sleeps when not in use
- **Container Support** - Run via Podman for easy deployment
- **Systemd Services** - Auto-start on boot with proper logging
- **CI/CD** - Automated linting and container builds via Forgejo

## Quick Start

### Prerequisites

- Raspberry Pi with 40-pin GPIO
- Pimoroni Weather HAT
- I2C and SPI enabled (`sudo raspi-config`)

### Install

```bash
git clone https://github.com/yourusername/weather-station.git
cd weather-station
sudo ./scripts/install-service.sh
```

The installer creates a `weather` service user, sets up the Python environment, and configures the systemd service. You'll be prompted to configure your MQTT broker settings.

### Verify

```bash
# Check service status
sudo systemctl status weatherhat

# View logs
sudo journalctl -u weatherhat -f

# Subscribe to MQTT topics (from another machine)
mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v
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
├── scripts/                # Installation scripts
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
MQTT_PASSWORD=secret
TEMP_OFFSET=-7.5
```

See [MQTT.md](docs/MQTT.md) for all options.

## MQTT Topics

```
sensors/weather/temperature      - Air temperature (°C)
sensors/weather/humidity         - Humidity (%)
sensors/weather/pressure         - Pressure (hPa)
sensors/weather/light            - Light (lux)
sensors/weather/wind_speed       - Wind speed (m/s)
sensors/weather/wind_direction   - Wind direction (cardinal)
sensors/weather/rain             - Rain rate (mm/s)
sensors/pi/cpu_temp              - CPU temperature (°C)
```

## Container Deployment

```bash
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  registry.timfinn.dev/weatherhat:latest
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
