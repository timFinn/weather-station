# Container Deployment

Run the Weather Station MQTT publisher in a container using Podman.

## Overview

The container image includes:
- Python 3.11 runtime
- All sensor libraries (weatherhat, BME280, LTR559, etc.)
- MQTT publisher script

The container requires access to the Pi's hardware devices (I2C, SPI, GPIO).

## Quick Start

```bash
# Pull the image
podman pull registry.timfinn.dev/weatherhat:latest

# Run with hardware access
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  registry.timfinn.dev/weatherhat:latest
```

## Building Locally

```bash
# Build the image
podman build -t weatherhat:latest -f Containerfile .

# Run locally built image
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  weatherhat:latest
```

## Configuration

Pass environment variables via `--env-file` or individual `-e` flags:

```bash
# Using env file
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file config/mqtt.env \
  registry.timfinn.dev/weatherhat:latest

# Using individual variables
podman run --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  -e MQTT_SERVER=mqtt.example.com \
  -e MQTT_PORT=1883 \
  -e MQTT_USERNAME=weatherhat \
  -e MQTT_PASSWORD=secret \
  -e TEMP_OFFSET=-7.5 \
  registry.timfinn.dev/weatherhat:latest
```

## Running as a Service

### With Podman Quadlet (Recommended)

Create `/etc/containers/systemd/weatherhat.container`:

```ini
[Unit]
Description=Weather HAT MQTT Publisher
After=network-online.target

[Container]
Image=registry.timfinn.dev/weatherhat:latest
AddDevice=/dev/i2c-1
AddDevice=/dev/spidev0.0
AddDevice=/dev/gpiochip0
SecurityLabelDisable=true
EnvironmentFile=/home/weather/weather-station/config/mqtt.env

[Service]
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now weatherhat
```

### With Podman Generate Systemd

```bash
# Create the container (don't start yet)
podman create --name weatherhat \
  --privileged \
  --device /dev/i2c-1 \
  --device /dev/spidev0.0 \
  --device /dev/gpiochip0 \
  --env-file /home/weather/weather-station/config/mqtt.env \
  registry.timfinn.dev/weatherhat:latest

# Generate systemd unit
podman generate systemd --name weatherhat --files --new

# Install and enable
sudo mv container-weatherhat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-weatherhat
```

## Device Access

The container needs access to these devices:

| Device | Purpose |
|--------|---------|
| `/dev/i2c-1` | I2C bus for BME280, LTR559, IO Expander |
| `/dev/spidev0.0` | SPI for LCD display |
| `/dev/gpiochip0` | GPIO for wind/rain sensors |

### Troubleshooting Device Access

```bash
# Check devices exist
ls -la /dev/i2c-1 /dev/spidev0.0 /dev/gpiochip0

# Check I2C is enabled
i2cdetect -y 1

# If devices missing, enable interfaces
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot
```

## Multi-Architecture Support

The CI pipeline builds images for both architectures:
- `linux/amd64` - For development/testing on x86
- `linux/arm64` - For Raspberry Pi deployment

Podman automatically pulls the correct architecture.

## CI/CD

Images are built and pushed automatically via Forgejo CI:

1. On push to `main`, the workflow runs
2. Linting checks (ruff, isort, codespell)
3. Multi-arch container build
4. Push to `registry.timfinn.dev/weatherhat:latest`

See `.forgejo/workflows/ci.yml` for details.

## Logs

```bash
# View container logs
podman logs weatherhat

# Follow logs
podman logs -f weatherhat

# If running as systemd service
journalctl -u container-weatherhat -f
```

## Updating

```bash
# Pull latest image
podman pull registry.timfinn.dev/weatherhat:latest

# Restart container
podman stop weatherhat
podman rm weatherhat
podman run ... # (same run command as before)

# Or if using systemd
sudo systemctl restart container-weatherhat
```

## Limitations

- **Display not supported**: The container runs only the MQTT publisher. The display interface requires direct framebuffer access and is not containerized.
- **Privileged mode**: Currently requires `--privileged` for GPIO access. Future versions may use more granular permissions.
