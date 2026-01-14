#!/bin/bash
# migrate-to-production.sh
# Migrates weatherhat-python from development structure to production structure

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "===== Weather HAT Production Structure Migration ====="
echo ""
echo "This script will reorganize your project structure:"
echo "  - Production scripts: examples/ → bin/"
echo "  - Configuration: examples/ → config/"
echo "  - Documentation: root/ → docs/"
echo ""
echo "Project root: $PROJECT_ROOT"
echo ""

# Confirmation
read -p "Continue with migration? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Migration cancelled."
    exit 0
fi

# Backup
echo ""
echo "Step 1/6: Creating backup..."
BACKUP_DIR="backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r examples "$BACKUP_DIR/" 2>/dev/null || true
cp *.md "$BACKUP_DIR/" 2>/dev/null || true
echo "✅ Backup created: $BACKUP_DIR"

# Create directories
echo ""
echo "Step 2/6: Creating new directory structure..."
mkdir -p bin config docs
echo "✅ Directories created: bin/, config/, docs/"

# Move production scripts
echo ""
echo "Step 3/6: Moving production scripts to bin/..."
if [ -f examples/mqtt.py ]; then
    mv examples/mqtt.py bin/mqtt-publisher.py
    echo "  ✅ mqtt.py → bin/mqtt-publisher.py"
fi

if [ -f examples/display.py ]; then
    mv examples/display.py bin/display-interface.py
    echo "  ✅ display.py → bin/display-interface.py"
fi

if [ -f examples/run-mqtt.sh ]; then
    mv examples/run-mqtt.sh bin/run-mqtt.sh
    echo "  ✅ run-mqtt.sh → bin/run-mqtt.sh"
fi

chmod +x bin/*.py bin/*.sh 2>/dev/null || true
echo "✅ Production scripts moved and marked executable"

# Move configuration
echo ""
echo "Step 4/6: Moving configuration to config/..."
if [ -f examples/mqtt.env.example ]; then
    mv examples/mqtt.env.example config/mqtt.env.example
    echo "  ✅ mqtt.env.example → config/mqtt.env.example"
fi

if [ -f examples/mqtt.env ]; then
    mv examples/mqtt.env config/mqtt.env
    chmod 600 config/mqtt.env
    echo "  ✅ mqtt.env → config/mqtt.env (secure permissions set)"
fi

# Create .gitignore in config/
cat > config/.gitignore << 'EOF'
# Ignore production environment files
mqtt.env

# Keep the example template
!mqtt.env.example
EOF
echo "  ✅ config/.gitignore created"
echo "✅ Configuration moved to config/"

# Update bin/run-mqtt.sh
echo ""
echo "Step 5/6: Updating bin/run-mqtt.sh paths..."
if [ -f bin/run-mqtt.sh ]; then
    cat > bin/run-mqtt.sh << 'EOF'
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
EOF
    chmod +x bin/run-mqtt.sh
    echo "✅ bin/run-mqtt.sh updated with new paths"
fi

# Move documentation
echo ""
echo "Step 6/6: Moving documentation to docs/..."
docs_moved=0

for doc in examples/MQTT_README.md examples/DISPLAY_README.md \
           QUICK_START.md SETUP_INSTRUCTIONS.md DISPLAY_SETUP.md \
           MIGRATION_CHECKLIST.md IMPROVEMENTS_SUMMARY.md IMPROVEMENTS_TODAY.md \
           DEV_FILES_GUIDE.md CLEANUP_GUIDE.md README-service-setup.md \
           REORGANIZATION_GUIDE.md; do
    if [ -f "$doc" ]; then
        filename=$(basename "$doc")
        mv "$doc" "docs/$filename"
        echo "  ✅ $filename → docs/"
        ((docs_moved++))
    fi
done

echo "✅ Documentation moved to docs/ ($docs_moved files)"

# Summary
echo ""
echo "===== Migration Complete! ====="
echo ""
echo "📁 New structure:"
echo "   bin/               - Production scripts (mqtt-publisher.py, display-interface.py)"
echo "   config/            - Configuration files (mqtt.env.example, mqtt.env)"
echo "   docs/              - All documentation"
echo "   examples/          - Reference examples only (adafruit-io.py, weather.py)"
echo ""
echo "📦 Backup location: $BACKUP_DIR"
echo ""
echo "⚠️  IMPORTANT: Manual steps required!"
echo ""
echo "1️⃣  Update systemd service files:"
echo "    sudo nano /etc/systemd/system/weatherhat.service"
echo ""
echo "    Change:"
echo "      WorkingDirectory=/home/garden/weatherhat-python/examples"
echo "      EnvironmentFile=/home/garden/weatherhat-python/examples/mqtt.env"
echo "      ExecStart=.../examples/mqtt.py"
echo ""
echo "    To:"
echo "      WorkingDirectory=/home/garden/weatherhat-python/bin"
echo "      EnvironmentFile=/home/garden/weatherhat-python/config/mqtt.env"
echo "      ExecStart=.../bin/mqtt-publisher.py"
echo ""
echo "2️⃣  Update display service:"
echo "    sudo nano /etc/systemd/system/weatherhat-display.service"
echo ""
echo "    Change:"
echo "      WorkingDirectory=/home/garden/weatherhat-python/examples"
echo "      ExecStart=.../examples/display.py"
echo ""
echo "    To:"
echo "      WorkingDirectory=/home/garden/weatherhat-python/bin"
echo "      ExecStart=.../bin/display-interface.py"
echo ""
echo "3️⃣  Reload systemd and restart services:"
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl restart weatherhat"
echo "    sudo systemctl restart weatherhat-display"
echo ""
echo "4️⃣  Verify services are running:"
echo "    sudo systemctl status weatherhat"
echo "    sudo systemctl status weatherhat-display"
echo "    journalctl -u weatherhat -n 50"
echo ""
echo "5️⃣  Update service files in repository (for version control):"
echo "    Edit: weatherhat.service"
echo "    Edit: weatherhat-display.service"
echo "    (Use the same path changes as above)"
echo ""
echo "📖 Full documentation: docs/REORGANIZATION_GUIDE.md"
echo ""
echo "🔄 To rollback (if needed):"
echo "    sudo systemctl stop weatherhat weatherhat-display"
echo "    rm -rf examples bin config docs"
echo "    cp -r $BACKUP_DIR/examples ."
echo "    # Restore old service files and restart"
echo ""
