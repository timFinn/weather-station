# Weather HAT Systemd Service Setup

This sets up your Weather HAT MQTT publisher as a proper systemd service, replacing the cron-based startup.

## Benefits over Cron

- **Proper dependency ordering**: Waits for network and time sync before starting
- **Automatic restarts**: Service restarts on failure with configurable backoff
- **Single instance guarantee**: No GPIO conflicts from duplicate processes
- **Better logging**: Integrated with journalctl for easy debugging
- **Resource limits**: Memory and CPU constraints protect your Pi Zero
- **Clean shutdown**: Graceful stop handling

## Files

| File | Purpose |
|------|---------|
| `install-dependencies.sh` | Installs all required packages (run first) |
| `weatherhat.service` | Systemd service definition |
| `install-service.sh` | Installs and enables the service |

## Installation Steps

### 1. Transfer files to Pi

```bash
scp install-dependencies.sh weatherhat.service install-service.sh garden@<pi-address>:~/
```

### 2. Install dependencies (if needed)

```bash
chmod +x install-dependencies.sh
./install-dependencies.sh
sudo reboot  # If this was a fresh install
```

### 3. Install the service

```bash
chmod +x install-service.sh
sudo ./install-service.sh
```

The installer will:
- Detect and offer to remove existing cron entries
- Install the systemd service
- Enable it to start on boot
- Optionally start it immediately

## Managing the Service

```bash
# Check status
sudo systemctl status weatherhat

# View logs (live)
sudo journalctl -u weatherhat -f

# View recent logs
sudo journalctl -u weatherhat -n 100

# Restart after code changes
sudo systemctl restart weatherhat

# Stop temporarily
sudo systemctl stop weatherhat

# Disable from starting at boot
sudo systemctl disable weatherhat
```

## Customization

### Adjusting startup delay

If GPIO initialization still fails, increase the `ExecStartPre` sleep:

```ini
ExecStartPre=/bin/sleep 30
```

### Changing restart behavior

The service restarts on failure with a 30-second delay. Modify in the `[Service]` section:

```ini
Restart=on-failure
RestartSec=30
StartLimitBurst=5          # Max 5 restarts...
StartLimitIntervalSec=300  # ...within 5 minutes
```

### Resource limits

Current limits are conservative for Pi Zero's 512MB RAM:

```ini
MemoryMax=128M
CPUQuota=50%
```

### Logging to file instead of journal

Replace the StandardOutput/StandardError lines:

```ini
StandardOutput=append:/home/garden/weatherhat.log
StandardError=append:/home/garden/weatherhat.log
```

## Troubleshooting

### Service fails to start

```bash
# Check detailed error
sudo journalctl -u weatherhat -n 50 --no-pager

# Test manually
source ~/.virtualenvs/pimoroni/bin/activate
python ~/weatherhat-python/examples/mqtt.py
```

### GPIO busy errors

Ensure no other process is using GPIO:

```bash
# Find processes using GPIO
sudo lsof /dev/gpiochip*
ps aux | grep mqtt

# Kill stuck processes
sudo pkill -f mqtt.py
```

### Network not ready

The service waits for `network-online.target`, but if your MQTT broker is slow:

```bash
# Add longer initial delay
sudo systemctl edit weatherhat
```

Add override:
```ini
[Service]
ExecStartPre=
ExecStartPre=/bin/sleep 45
```
