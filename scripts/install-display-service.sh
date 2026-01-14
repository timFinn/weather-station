#!/bin/bash
# install-display-service.sh
# Installs the Weather HAT display service

set -e

SERVICE_NAME="weatherhat-display"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_SERVICE="$PROJECT_ROOT/weatherhat-display.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
prompt() { echo -e "${BLUE}[?]${NC} $1"; }

# Check for root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root: sudo $0"
    exit 1
fi

# Check service file exists
if [ ! -f "$SOURCE_SERVICE" ]; then
    error "Service file not found: $SOURCE_SERVICE"
    exit 1
fi

echo "=========================================="
echo "Weather HAT Display Service Installer"
echo "=========================================="
echo ""
info "Project root: $PROJECT_ROOT"
echo ""

# Check font dependencies
check_fonts() {
    info "Checking font dependencies..."

    SERVICE_USER=$(grep "^User=" "$SOURCE_SERVICE" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    SERVICE_USER=${SERVICE_USER:-garden}

    VENV_PATH="/home/$SERVICE_USER/.virtualenvs/pimoroni"

    if [ ! -d "$VENV_PATH" ]; then
        warn "Virtual environment not found at $VENV_PATH"
        warn "Run install-dependencies.sh first"
        return 1
    fi

    # Check for font packages
    if ! sudo -u "$SERVICE_USER" "$VENV_PATH/bin/python" -c "import fonts" 2>/dev/null; then
        warn "Font packages not installed"
        echo ""
        prompt "Install font packages now? [Y/n] "
        read -p "" -n 1 -r
        echo ""

        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            info "Installing fonts..."
            sudo -u "$SERVICE_USER" "$VENV_PATH/bin/pip" install fonts font-manrope
        fi
    else
        info "Font packages installed"
    fi
}

# Stop existing service if running
stop_existing() {
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Stopping existing $SERVICE_NAME service..."
        systemctl stop "$SERVICE_NAME"
    fi
}

# Install the service file
install_service() {
    info "Installing service file to $SERVICE_FILE..."
    cp "$SOURCE_SERVICE" "$SERVICE_FILE"
    chmod 644 "$SERVICE_FILE"

    info "Reloading systemd daemon..."
    systemctl daemon-reload
}

# Enable and start service
enable_service() {
    info "Enabling $SERVICE_NAME to start on boot..."
    systemctl enable "$SERVICE_NAME"

    read -p "Start service now? [Y/n] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        info "Starting $SERVICE_NAME service..."
        systemctl start "$SERVICE_NAME"
        sleep 3

        echo ""
        info "Service status:"
        systemctl status "$SERVICE_NAME" --no-pager -l || true
    fi
}

# Show useful commands
show_commands() {
    echo ""
    echo "=========================================="
    info "Installation complete!"
    echo "=========================================="
    echo ""
    echo "Display Features:"
    echo "  - Sleeps by default (power saving)"
    echo "  - Press any button to wake"
    echo "  - A: Overview | B: Temp | X: Wind | Y: Rain"
    echo "  - Auto-sleep after 30 seconds"
    echo ""
    echo "Useful commands:"
    echo ""
    echo "  # Check service status"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo ""
    echo "  # View live logs"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "  # Restart service"
    echo "  sudo systemctl restart $SERVICE_NAME"
    echo ""
    echo "  # Stop service"
    echo "  sudo systemctl stop $SERVICE_NAME"
    echo ""
    echo "  # Test manually"
    echo "  cd $PROJECT_ROOT/examples"
    echo "  source ~/.virtualenvs/pimoroni/bin/activate"
    echo "  python3 display.py"
    echo ""
    echo "Configuration:"
    echo "  Edit: /etc/systemd/system/$SERVICE_NAME.service"
    echo "  Environment variables:"
    echo "    - TEMP_OFFSET=-7.5"
    echo "    - DISPLAY_SLEEP_TIMEOUT=30"
    echo ""
    echo "Documentation:"
    echo "  See: $PROJECT_ROOT/examples/DISPLAY_README.md"
    echo ""
}

# Main
main() {
    check_fonts
    echo ""
    stop_existing
    echo ""
    install_service
    echo ""
    enable_service
    echo ""
    show_commands
}

main "$@"
