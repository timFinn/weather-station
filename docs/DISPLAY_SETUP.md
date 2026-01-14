# Weather HAT Display Setup - Quick Guide

## What You Get

A **power-efficient display interface** that:
- 💤 Sleeps by default (backlight off)
- 👆 Wakes on any button press
- 📊 Shows live weather overview
- 📈 Displays historical graphs
- ⏰ Auto-sleeps after 30 seconds
- 🔄 Runs alongside your MQTT publisher

## Installation

### Option 1: Automated (Recommended)

```bash
cd ~/weatherhat-python/scripts
sudo ./install-display-service.sh
```

The script will:
1. Check font dependencies
2. Install systemd service
3. Configure auto-start
4. Show you how to use it

### Option 2: Manual Test First

```bash
cd ~/weatherhat-python/examples
source ~/.virtualenvs/pimoroni/bin/activate
python3 display.py
```

Press any button to wake the display!

## Button Controls

```
┌─────────────────────────────────┐
│  Button A  →  Live Overview     │
│  Button B  →  Temperature Graph │
│  Button X  →  Wind Speed Graph  │
│  Button Y  →  Rain Rate Graph   │
│                                 │
│  Any Button → Wake from Sleep   │
└─────────────────────────────────┘
```

## Usage

Once installed as a service:

```bash
# Check it's running
sudo systemctl status weatherhat-display

# Watch what it's doing
sudo journalctl -u weatherhat-display -f

# Restart if needed
sudo systemctl restart weatherhat-display
```

## Customization

Edit sleep timeout in service file:
```bash
sudo nano /etc/systemd/system/weatherhat-display.service
```

Change this line:
```
Environment="DISPLAY_SLEEP_TIMEOUT=30"
```

To something like:
```
Environment="DISPLAY_SLEEP_TIMEOUT=60"  # 1 minute
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart weatherhat-display
```

## Running Both Services

Your Pi can run both simultaneously:

```bash
# MQTT publisher + Display
sudo systemctl status weatherhat weatherhat-display

# View combined logs
sudo journalctl -u weatherhat -u weatherhat-display -f
```

They share the sensor safely through proper locking.

## Troubleshooting

### Display won't wake
```bash
# Check service is running
sudo systemctl status weatherhat-display

# Check for errors
sudo journalctl -u weatherhat-display -n 50

# Test buttons
cd ~/weatherhat-python/examples
source ~/.virtualenvs/pimoroni/bin/activate
python3 buttons.py
```

### Font errors
```bash
source ~/.virtualenvs/pimoroni/bin/activate
pip install fonts font-manrope
```

### SPI not enabled
```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

## Architecture

```
Your Raspberry Pi
├─ weatherhat.service        → Publishes to MQTT
└─ weatherhat-display.service → Shows on LCD

Both read from same sensors safely!
```

## Power Consumption

- **Sleeping**: ~5mA (minimal)
- **Awake**: ~100-150mA (backlight on)
- **Average**: ~10-15mA (with 30s auto-sleep)

Very efficient!

## Files Created

```
weatherhat-python/
├── examples/
│   ├── display.py              ← Main display script
│   └── DISPLAY_README.md       ← Full documentation
├── scripts/
│   └── install-display-service.sh ← Installer
└── weatherhat-display.service  ← Systemd config
```

## Next Steps

1. **Test manually** to see it work
2. **Install service** for auto-start
3. **Adjust sleep timeout** if needed
4. **Customize colors/views** in display.py

See [examples/DISPLAY_README.md](examples/DISPLAY_README.md) for full documentation!
