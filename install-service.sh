#!/bin/bash
# install-service.sh
# Installs the Weather HAT systemd service and removes old cron-based startup

set -e

SERVICE_NAME="weatherhat"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SOURCE_SERVICE="./weatherhat.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check for root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root: sudo $0"
    exit 1
fi

# Check service file exists
if [ ! -f "$SOURCE_SERVICE" ]; then
    error "Service file not found: $SOURCE_SERVICE"
    error "Make sure weatherhat.service is in the current directory"
    exit 1
fi

echo "=========================================="
echo "Weather HAT Service Installer"
echo "=========================================="
echo ""

# Remove old cron job if it exists
remove_cron() {
    info "Checking for existing cron jobs..."
    
    # Check garden user's crontab
    if sudo -u garden crontab -l 2>/dev/null | grep -q "mqtt.py\|weatherhat"; then
        warn "Found existing cron entry for weather station"
        echo ""
        echo "Current cron entries:"
        sudo -u garden crontab -l 2>/dev/null | grep -E "mqtt|weather" || true
        echo ""
        
        read -p "Remove cron entries? [y/N] " -n 1 -r
        echo ""
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Remove lines containing mqtt.py or weatherhat from crontab
            sudo -u garden crontab -l 2>/dev/null | grep -v -E "mqtt\.py|weatherhat" | sudo -u garden crontab - || true
            info "Cron entries removed"
        else
            warn "Keeping cron entries - you may have duplicate startup!"
        fi
    else
        info "No existing cron entries found"
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
    echo "Useful commands:"
    echo ""
    echo "  # Check service status"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo ""
    echo "  # View live logs"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "  # View recent logs"
    echo "  sudo journalctl -u $SERVICE_NAME -n 50"
    echo ""
    echo "  # Restart service"
    echo "  sudo systemctl restart $SERVICE_NAME"
    echo ""
    echo "  # Stop service"
    echo "  sudo systemctl stop $SERVICE_NAME"
    echo ""
    echo "  # Disable service from starting at boot"
    echo "  sudo systemctl disable $SERVICE_NAME"
    echo ""
}

# Main
main() {
    remove_cron
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
