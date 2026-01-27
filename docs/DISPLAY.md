# Weather HAT Display Interface

A power-efficient LCD display interface that shows weather data locally on the Weather HAT's 1.54" screen.

## Features

- **Sleep mode by default** - Backlight off to save power
- **Button wake** - Any button turns on the display
- **Live overview** - Current readings at a glance
- **Historical graphs** - View trends over the last 10 minutes
- **Auto-sleep** - Returns to sleep after 30 seconds of inactivity
- **Independent** - Runs alongside MQTT publisher without interference

## Installation

### Automated Install

```bash
cd /path/to/weather-station
sudo ./scripts/install-display-service.sh
```

The script will:
1. Check that the main service is already installed
2. Verify font dependencies
3. Install the systemd service
4. Enable auto-start

### Manual Test

Test the display before installing as a service:

```bash
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/display-interface.py
```

Press any button to wake the display.

## Button Controls

| Button | Function |
|--------|----------|
| **A** | Overview screen (live data) |
| **B** | Temperature history graph |
| **X** | Wind speed history graph |
| **Y** | Rain rate history graph |
| **Any** | Wake display from sleep |

## Screens

### Overview Screen (Button A)

```
┌─────────────────────────┐
│       WEATHER           │
│                         │
│        23.5°C           │  ← Large temperature
│                         │
│  45%      1013   1.2    │  ← Humidity, Pressure, Wind
│  Humidity  hPa   m/s    │
│                         │
│  NE       0.0    1234   │  ← Wind Dir, Rain, Light
│  Wind    mm/s    lux    │
│                         │
│  B:Temp X:Wind Y:Rain   │  ← Button hints
└─────────────────────────┘
```

### History Graph (Buttons B/X/Y)

```
┌─────────────────────────┐
│    TEMPERATURE          │
│                         │
│        23.5°C           │  ← Current value
│                         │
│ 25  ┌─────────╱──╲      │
│     │        ╱    ╲     │  ← 10-minute graph
│     │    ╱──╯      ╲    │
│ 20  └────────────────   │
│                         │
│  Last 600s • A:Overview │
└─────────────────────────┘
```

## Service Management

```bash
# Check status
sudo systemctl status weatherhat-display

# View logs
sudo journalctl -u weatherhat-display -f

# Restart
sudo systemctl restart weatherhat-display

# Stop
sudo systemctl stop weatherhat-display

# Disable auto-start
sudo systemctl disable weatherhat-display
```

## Running Both Services

The MQTT publisher and display can run simultaneously:

```bash
# Check both services
sudo systemctl status weatherhat weatherhat-display

# View combined logs
sudo journalctl -u weatherhat -u weatherhat-display -f

# Monitor status
watch -n1 'systemctl is-active weatherhat weatherhat-display'
```

Both services share the sensor hardware safely through the weatherhat library's built-in locking.

## Configuration

Environment variables (set in the service file):

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMP_OFFSET` | `-7.5` | Temperature compensation offset |
| `DISPLAY_SLEEP_TIMEOUT` | `30` | Seconds before auto-sleep |

To change settings:

```bash
sudo nano /etc/systemd/system/weatherhat-display.service
# Edit Environment= lines
sudo systemctl daemon-reload
sudo systemctl restart weatherhat-display
```

## Customization

### Change Sleep Timeout

Edit the service file or set environment variable:

```bash
export DISPLAY_SLEEP_TIMEOUT=60  # 1 minute
```

### Adjust Graph History

In `bin/display-interface.py`:

```python
self.temp_history = history.History(history_depth=600)  # 20 minutes at 2s intervals
```

### Change Colors

In `bin/display-interface.py`:

```python
COLOR_YELLOW = (254, 219, 82)  # Temperature
COLOR_CYAN = (0, 255, 255)     # Wind
COLOR_BLUE = (31, 137, 251)    # Rain
```

## Power Consumption

| State | Current Draw |
|-------|--------------|
| Sleeping | ~5mA (backlight off) |
| Awake | ~100-150mA (backlight on) |
| Average (30s on, 5min off) | ~10-15mA |

## Performance

- **Sensor updates**: Every 2 seconds
- **Display refresh**: 5 FPS when awake
- **History retention**: 10 minutes (300 data points)
- **CPU usage**: <1% sleeping, ~5-10% when awake
- **Memory**: ~40-60MB

## Troubleshooting

### Display Stays Black

```bash
# Check service is running
sudo systemctl status weatherhat-display

# Check for errors
sudo journalctl -u weatherhat-display -n 50

# Test manually
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/bin/display-interface.py
```

### Font Errors

```bash
source /home/weather/.virtualenvs/pimoroni/bin/activate
pip install fonts font-manrope
```

### SPI Errors

```bash
# Enable SPI
sudo raspi-config nonint do_spi 0
sudo reboot
```

### Display Flickers

Lower SPI speed in `bin/display-interface.py`:

```python
SPI_SPEED_MHZ = 40  # Instead of 80
```

### Buttons Not Working

Test buttons directly:

```bash
sudo -u weather /home/weather/.virtualenvs/pimoroni/bin/python \
  /home/weather/weather-station/examples/buttons.py
```

## Architecture

```
┌─────────────────────────────────────────┐
│  Weather HAT Hardware                   │
│  ├─ Sensors (BME280, LTR559, etc.)      │
│  ├─ LCD Display (ST7789)                │
│  └─ Buttons (A, B, X, Y)                │
└────────────┬────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
┌───▼────────┐  ┌────▼──────────────┐
│ weatherhat │  │ weatherhat-display│
│ service    │  │ service           │
│            │  │                   │
│ Publishes  │  │ Shows on LCD      │
│ to MQTT    │  │ - Live overview   │
│ broker     │  │ - History graphs  │
│            │  │ - Sleep/wake      │
└────────────┘  └───────────────────┘
```
