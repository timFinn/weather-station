# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment

This repository is developed on a remote dev machine, NOT on the Raspberry Pi. Code cannot be run or tested locally — it must be deployed to the Pi. Do not attempt to run service commands (systemctl, journalctl) or hardware-dependent scripts locally.

## Project Overview

A Python library and IoT system for reading weather sensor data from a Pimoroni Weather HAT on Raspberry Pi and publishing to MQTT. Includes MQTT publisher service and display interface.

## Key Commands

```bash
# Activate virtual environment
# On dev machine:
source .venv/bin/activate
# On Raspberry Pi:
# source ~/.virtualenvs/pimoroni/bin/activate

# Run MQTT publisher manually
python3 bin/mqtt-publisher.py

# Run display interface
python3 bin/display-interface.py

# Run example weather display
python3 examples/weather.py

# Service management
sudo systemctl status weatherhat
sudo systemctl restart weatherhat
sudo journalctl -u weatherhat -f

# Install as systemd service
sudo ./scripts/install-service.sh
sudo ./scripts/install-display-service.sh

# Update deployment (pull latest, sync, restart)
sudo ./scripts/update.sh

# Run MQTT diagnostics
sudo ./scripts/test-mqtt.sh

# Enable I2C and SPI (required for hardware)
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
```

## CI/CD

Forgejo workflows in `.forgejo/workflows/`:
- **ci.yml** - Runs linting, builds and pushes multi-arch container image

```bash
# Run linting locally
pip install ruff codespell isort
ruff check .
isort --check-only --diff .
codespell --skip='.git,*.pyc,__pycache__,dist,build,.tox,.egg'

# Build container locally with Podman
podman build -t weatherhat:latest -f Containerfile .

# Run container on Pi (requires device access)
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  weatherhat:latest
```

## Code Quality

Configured in `pyproject.toml`:
- **ruff** - linter (line-length: 200)
- **isort** - import sorting (line-length: 200)
- **codespell** - spell checker

## Architecture

### Directory Structure
- `bin/` - Production executables (mqtt-publisher.py, display-interface.py)
- `config/` - Environment configuration (mqtt.env)
- `docs/` - Documentation (SETUP.md, MQTT.md, DISPLAY.md, CONTAINER.md)
- `examples/` - Reference examples and demos
- `scripts/` - Installation, update, and diagnostic scripts
- `weatherhat/` - Core sensor library
- `.forgejo/workflows/` - CI/CD workflows
- `Containerfile` - Container build for Podman deployment

### Core Components

**WeatherHAT Library** (`weatherhat/__init__.py`):
- Main sensor interface managing I2C/SPI communication
- BME280 for temperature/humidity/pressure
- LTR559 for light sensing
- IO Expander for wind/rain sensors via GPIO interrupts
- Thread-safe counter access with locks

**MQTT Publisher** (`bin/mqtt-publisher.py`):
- Reads sensors via WeatherHAT class
- Publishes to MQTT broker with QoS 1
- Automatic reconnection via paho network loop with exponential backoff (1s → 5min max)
- I2C error recovery: catches OSError, RuntimeError, SensorTimeout → attempts bus recovery at 3 errors, exits at 5 for systemd restart
- Diagnostic logging on sensor errors: power/throttle state, I2C bus scan, uptime and timing
- SIGALRM timeout on sensor reads and initialization to prevent hangs
- LWT (Last Will and Testament) for online/offline status on `sensors/weather/status`
- Graceful shutdown handling (SIGINT/SIGTERM)
- Configured via environment variables

**History Classes** (`weatherhat/history.py`):
- Data aggregation for min/max/average over time
- Unit conversions (m/s to mph/km/h for wind)
- Used by display for historical graphs

### Data Flow
```
Hardware Sensors → WeatherHAT class → MQTT Publisher → MQTT Broker → Remote consumers
                                   ↘ Display Interface    ↓              ↓
                                     (local visualization) Telegraf    LWT status
                                                           ↓
                                                        InfluxDB (bucket: "weather")
                                                           ↓
                                                        Grafana → Discord alerts
```

### Threading Model
- Main thread: Sensor reads, MQTT publishing, display updates
- Polling thread: Monitors GPIO for wind/rain interrupts (thread-safe with locks)

## Configuration

Environment variables for MQTT publisher (set in `config/mqtt.env`):
- `MQTT_SERVER` - broker hostname (default: localhost)
- `MQTT_PORT` - broker port (default: 1883)
- `MQTT_USERNAME`/`MQTT_PASSWORD` - optional auth
- `MQTT_CLIENT_ID` - client identifier (default: weatherhat-{hostname}, must be unique across all MQTT clients)
- `MQTT_TOPIC_PREFIX` - topic prefix (default: sensors)
- `TEMP_OFFSET` - temperature compensation (default: -7.5°C)
- `UPDATE_INTERVAL`/`PUBLISH_INTERVAL` - timing in seconds

## Deployment

When deploying fixes to remote devices (Raspberry Pi, weather stations), always update the deployment/sync scripts (e.g., update.sh, sdr-update.sh) to include any new files or dependencies. Verify the full deployment pipeline, not just the local fix.

## Debugging Patterns

When debugging services (MQTT, WebSocket, background threads): suspect threading/process lifecycle issues first (zombie processes, race conditions with reconnect loops, sys.exit not killing threads). Use os._exit() for daemon processes with background threads.

## Hardware Requirements

- Raspberry Pi with 40-pin GPIO header
- Pimoroni Weather HAT
- I2C and SPI must be enabled
- Python ≥ 3.7
