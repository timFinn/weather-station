# Production Repository Reorganization Guide

## Overview

This guide helps you reorganize the weatherhat-python repository from a development/example-focused structure to a production-ready structure.

## Current vs. Proposed Structure

### Current Structure (Development-Focused)
```
weatherhat-python/
├── examples/              # Mix of production code and demos
│   ├── mqtt.py           # ⚠️ Production code in examples!
│   ├── display.py        # ⚠️ Production code in examples!
│   ├── mqtt.env.example  # ⚠️ Config in examples!
│   ├── run-mqtt.sh       # ⚠️ Production script in examples!
│   ├── adafruit-io.py    # Actual example
│   ├── weather.py        # Actual example
│   └── ...
```

### Proposed Structure (Production-Ready)
```
weatherhat-python/
├── bin/                   # ✅ Production executables
│   ├── mqtt-publisher.py
│   ├── display-interface.py
│   └── run-mqtt.sh
├── config/                # ✅ Configuration management
│   ├── mqtt.env.example
│   └── .gitignore
├── docs/                  # ✅ All documentation
│   ├── MQTT_README.md
│   ├── DISPLAY_README.md
│   ├── QUICK_START.md
│   ├── SETUP_INSTRUCTIONS.md
│   ├── DISPLAY_SETUP.md
│   ├── MIGRATION_CHECKLIST.md
│   ├── IMPROVEMENTS_SUMMARY.md
│   ├── DEV_FILES_GUIDE.md
│   └── CLEANUP_GUIDE.md
├── examples/              # ✅ Reference examples only
│   ├── adafruit-io.py
│   ├── weather.py
│   ├── settings.yml
│   └── icons/
├── scripts/               # Existing installation scripts
├── weatherhat/            # Existing library code
├── weatherhat.service
├── weatherhat-display.service
└── pyproject.toml
```

## Benefits of Reorganization

1. **Clarity**: Production code clearly separated from examples
2. **Maintainability**: Easier to find what you need
3. **Security**: Config directory makes secret management clearer
4. **Standards**: Follows common conventions (`bin/` for executables)
5. **Onboarding**: New users/developers understand structure immediately
6. **Documentation**: All docs in one place

## Migration Steps

### Step 1: Create New Directories

```bash
cd ~/weatherhat-python
mkdir -p bin config docs
```

### Step 2: Move Production Scripts

```bash
# Move production code
mv examples/mqtt.py bin/mqtt-publisher.py
mv examples/display.py bin/display-interface.py
mv examples/run-mqtt.sh bin/run-mqtt.sh

# Update permissions
chmod +x bin/mqtt-publisher.py
chmod +x bin/display-interface.py
chmod +x bin/run-mqtt.sh
```

### Step 3: Move Configuration

```bash
# Move config template
mv examples/mqtt.env.example config/mqtt.env.example

# If you have a production mqtt.env, move it too
if [ -f examples/mqtt.env ]; then
    mv examples/mqtt.env config/mqtt.env
    chmod 600 config/mqtt.env
fi

# Create .gitignore in config/
cat > config/.gitignore << 'EOF'
# Ignore production environment files
mqtt.env

# Keep the example template
!mqtt.env.example
EOF
```

### Step 4: Move Documentation

```bash
# Move all markdown docs to docs/
mv examples/MQTT_README.md docs/
mv examples/DISPLAY_README.md docs/
mv QUICK_START.md docs/
mv SETUP_INSTRUCTIONS.md docs/
mv DISPLAY_SETUP.md docs/
mv MIGRATION_CHECKLIST.md docs/
mv IMPROVEMENTS_SUMMARY.md docs/
mv IMPROVEMENTS_TODAY.md docs/
mv DEV_FILES_GUIDE.md docs/
mv CLEANUP_GUIDE.md docs/
mv README-service-setup.md docs/

# Keep README.md in root
# Keep CHANGELOG.md in root (if exists)
```

### Step 5: Update Systemd Services

**weatherhat.service:**
```bash
sudo nano /etc/systemd/system/weatherhat.service
```

Change:
```ini
WorkingDirectory=/home/garden/weatherhat-python/examples
EnvironmentFile=/home/garden/weatherhat-python/examples/mqtt.env
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/examples/mqtt.py
```

To:
```ini
WorkingDirectory=/home/garden/weatherhat-python/bin
EnvironmentFile=/home/garden/weatherhat-python/config/mqtt.env
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/bin/mqtt-publisher.py
```

**weatherhat-display.service:**
```bash
sudo nano /etc/systemd/system/weatherhat-display.service
```

Change:
```ini
WorkingDirectory=/home/garden/weatherhat-python/examples
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/examples/display.py
```

To:
```ini
WorkingDirectory=/home/garden/weatherhat-python/bin
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/bin/display-interface.py
```

**Reload systemd:**
```bash
sudo systemctl daemon-reload
```

### Step 6: Update Service Files in Repository

**weatherhat.service (in repo):**
```ini
[Unit]
Description=Weather HAT MQTT Publisher
After=network.target

[Service]
Type=simple
User=garden
Group=garden
WorkingDirectory=/home/garden/weatherhat-python/bin
EnvironmentFile=/home/garden/weatherhat-python/config/mqtt.env
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/bin/mqtt-publisher.py
Restart=always
RestartSec=10
CPUQuota=25%
MemoryLimit=128M

[Install]
WantedBy=multi-user.target
```

**weatherhat-display.service (in repo):**
```ini
[Unit]
Description=Weather HAT Display Interface
After=network.target weatherhat.service

[Service]
Type=simple
User=garden
Group=garden
WorkingDirectory=/home/garden/weatherhat-python/bin
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weatherhat-display
ExecStart=/home/garden/.virtualenvs/pimoroni/bin/python /home/garden/weatherhat-python/bin/display-interface.py
Restart=always
RestartSec=10
CPUQuota=50%
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
```

### Step 7: Update Installation Scripts

**scripts/install-service.sh:**

Change:
```bash
EXAMPLES_DIR="$PROJECT_ROOT/examples"
```

To:
```bash
BIN_DIR="$PROJECT_ROOT/bin"
CONFIG_DIR="$PROJECT_ROOT/config"
```

Update all paths in the script accordingly.

**scripts/install-display-service.sh:**

Update paths from `examples/` to `bin/` and `config/`.

### Step 8: Update bin/run-mqtt.sh

```bash
#!/bin/bash
# Helper script to run MQTT publisher with environment loaded

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_ROOT/config"
ENV_FILE="$CONFIG_DIR/mqtt.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file not found at $ENV_FILE"
    echo "Copy $CONFIG_DIR/mqtt.env.example to $ENV_FILE and configure it"
    exit 1
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Run the MQTT publisher
python "$SCRIPT_DIR/mqtt-publisher.py"
```

### Step 9: Update Documentation References

Update all documentation files to reference new paths:
- `examples/mqtt.py` → `bin/mqtt-publisher.py`
- `examples/display.py` → `bin/display-interface.py`
- `examples/mqtt.env` → `config/mqtt.env`
- `examples/mqtt.env.example` → `config/mqtt.env.example`

### Step 10: Test Everything

```bash
# Test MQTT publisher manually
cd ~/weatherhat-python/bin
source ../config/mqtt.env
python mqtt-publisher.py

# Test display manually
python display-interface.py

# Test services
sudo systemctl restart weatherhat
sudo systemctl status weatherhat

sudo systemctl restart weatherhat-display
sudo systemctl status weatherhat-display

# Check logs
journalctl -u weatherhat -n 50
journalctl -u weatherhat-display -n 50
```

## Files Affected by Reorganization

### Production Files (Move)
- ✅ `examples/mqtt.py` → `bin/mqtt-publisher.py`
- ✅ `examples/display.py` → `bin/display-interface.py`
- ✅ `examples/run-mqtt.sh` → `bin/run-mqtt.sh`
- ✅ `examples/mqtt.env.example` → `config/mqtt.env.example`
- ✅ `examples/mqtt.env` → `config/mqtt.env` (if exists)

### Documentation Files (Move)
- ✅ `examples/MQTT_README.md` → `docs/MQTT_README.md`
- ✅ `examples/DISPLAY_README.md` → `docs/DISPLAY_README.md`
- ✅ `QUICK_START.md` → `docs/QUICK_START.md`
- ✅ `SETUP_INSTRUCTIONS.md` → `docs/SETUP_INSTRUCTIONS.md`
- ✅ `DISPLAY_SETUP.md` → `docs/DISPLAY_SETUP.md`
- ✅ All other *.md guides → `docs/`

### Example Files (Keep in examples/)
- ⏹️ `examples/adafruit-io.py` - Keep
- ⏹️ `examples/weather.py` - Keep
- ⏹️ `examples/settings.yml` - Keep
- ⏹️ `examples/icons/` - Keep

### Service Files (Update)
- 🔧 `weatherhat.service` - Update paths
- 🔧 `weatherhat-display.service` - Update paths
- 🔧 `/etc/systemd/system/weatherhat.service` - Update paths
- 🔧 `/etc/systemd/system/weatherhat-display.service` - Update paths

### Installation Scripts (Update)
- 🔧 `scripts/install-service.sh`
- 🔧 `scripts/install-display-service.sh`
- 🔧 `scripts/install-dependencies.sh`

### Documentation (Update references)
- 🔧 `docs/QUICK_START.md`
- 🔧 `docs/SETUP_INSTRUCTIONS.md`
- 🔧 `docs/DISPLAY_SETUP.md`
- 🔧 `docs/MQTT_README.md`
- 🔧 `docs/DISPLAY_README.md`
- 🔧 `README.md`

## Automated Migration Script

Want to automate this? Here's a complete migration script:

```bash
#!/bin/bash
# migrate-to-production-structure.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "===== Weather HAT Production Structure Migration ====="
echo ""

# Backup
echo "Creating backup..."
BACKUP_DIR="backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r examples "$BACKUP_DIR/"
echo "✅ Backup created: $BACKUP_DIR"
echo ""

# Create directories
echo "Creating new directory structure..."
mkdir -p bin config docs
echo "✅ Directories created: bin/, config/, docs/"
echo ""

# Move production scripts
echo "Moving production scripts..."
mv examples/mqtt.py bin/mqtt-publisher.py
mv examples/display.py bin/display-interface.py
mv examples/run-mqtt.sh bin/run-mqtt.sh
chmod +x bin/*.py bin/*.sh
echo "✅ Production scripts moved to bin/"
echo ""

# Move configuration
echo "Moving configuration..."
mv examples/mqtt.env.example config/mqtt.env.example
if [ -f examples/mqtt.env ]; then
    mv examples/mqtt.env config/mqtt.env
    chmod 600 config/mqtt.env
    echo "✅ Production mqtt.env moved (with secure permissions)"
fi

cat > config/.gitignore << 'EOF'
# Ignore production environment files
mqtt.env

# Keep the example template
!mqtt.env.example
EOF
echo "✅ Configuration moved to config/"
echo ""

# Move documentation
echo "Moving documentation..."
mv examples/MQTT_README.md docs/ 2>/dev/null || true
mv examples/DISPLAY_README.md docs/ 2>/dev/null || true
mv QUICK_START.md docs/ 2>/dev/null || true
mv SETUP_INSTRUCTIONS.md docs/ 2>/dev/null || true
mv DISPLAY_SETUP.md docs/ 2>/dev/null || true
mv MIGRATION_CHECKLIST.md docs/ 2>/dev/null || true
mv IMPROVEMENTS_SUMMARY.md docs/ 2>/dev/null || true
mv IMPROVEMENTS_TODAY.md docs/ 2>/dev/null || true
mv DEV_FILES_GUIDE.md docs/ 2>/dev/null || true
mv CLEANUP_GUIDE.md docs/ 2>/dev/null || true
mv README-service-setup.md docs/ 2>/dev/null || true
echo "✅ Documentation moved to docs/"
echo ""

echo "===== Migration Complete! ====="
echo ""
echo "⚠️  IMPORTANT: Next steps required:"
echo ""
echo "1. Update systemd services:"
echo "   sudo nano /etc/systemd/system/weatherhat.service"
echo "   sudo nano /etc/systemd/system/weatherhat-display.service"
echo ""
echo "2. Update paths in service files (see REORGANIZATION_GUIDE.md)"
echo ""
echo "3. Reload systemd:"
echo "   sudo systemctl daemon-reload"
echo ""
echo "4. Test services:"
echo "   sudo systemctl restart weatherhat"
echo "   sudo systemctl status weatherhat"
echo ""
echo "📁 Backup location: $BACKUP_DIR"
echo "📖 Full guide: REORGANIZATION_GUIDE.md"
```

## Rollback (If Needed)

If something goes wrong:

```bash
# Stop services
sudo systemctl stop weatherhat weatherhat-display

# Restore from backup
cd ~/weatherhat-python
BACKUP_DIR="backup-20260114-120000"  # Use your actual backup dir
rm -rf examples
cp -r "$BACKUP_DIR/examples" .

# Revert service files
sudo systemctl daemon-reload
sudo systemctl start weatherhat weatherhat-display
```

## Post-Migration Cleanup

After confirming everything works:

```bash
# Remove backup
rm -rf backup-*

# Remove old development files (if desired)
rm tox.ini Makefile check.sh requirements-dev.txt .coveragerc
```

## Summary

**What moves:**
- Production scripts: `examples/` → `bin/`
- Configuration: `examples/` → `config/`
- Documentation: `root/` → `docs/`

**What stays:**
- Examples: `examples/` (adafruit-io.py, weather.py, etc.)
- Library: `weatherhat/`
- Installation: `scripts/`
- Core files: `pyproject.toml`, `README.md`, etc.

**What updates:**
- Service files (both in repo and `/etc/systemd/system/`)
- Installation scripts
- Documentation references

This reorganization makes your project production-ready while preserving the example code for reference! 🚀
