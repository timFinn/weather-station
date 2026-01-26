#!/bin/bash
# install-service.sh
# Installs the Weather HAT systemd service with environment configuration

set -e

SERVICE_NAME="weatherhat"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_SERVICE="$PROJECT_ROOT/weatherhat.service"
CONFIG_DIR="$PROJECT_ROOT/config"
BIN_DIR="$PROJECT_ROOT/bin"
ENV_EXAMPLE="$CONFIG_DIR/mqtt.env.example"
ENV_FILE="$CONFIG_DIR/mqtt.env"

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
echo "Weather HAT Service Installer (Improved)"
echo "=========================================="
echo ""
info "Project root: $PROJECT_ROOT"
echo ""

# Check and setup environment file
setup_environment() {
    info "Checking environment configuration..."

    if [ ! -f "$ENV_FILE" ]; then
        warn "Environment file not found: $ENV_FILE"

        if [ -f "$ENV_EXAMPLE" ]; then
            echo ""
            prompt "Would you like to create it from the example template?"
            read -p "Create mqtt.env? [Y/n] " -n 1 -r
            echo ""

            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                cp "$ENV_EXAMPLE" "$ENV_FILE"
                chmod 600 "$ENV_FILE"
                info "Created $ENV_FILE from template"
                echo ""
                warn "⚠️  IMPORTANT: You must edit $ENV_FILE before starting the service!"
                echo ""
                echo "Required settings:"
                echo "  - MQTT_SERVER (your MQTT broker hostname/IP)"
                echo "  - MQTT_USERNAME (if authentication required)"
                echo "  - MQTT_PASSWORD (if authentication required)"
                echo "  - TEMP_OFFSET (temperature compensation, default -7.5)"
                echo ""
                prompt "Edit the file now? [Y/n] "
                read -p "" -n 1 -r
                echo ""

                if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                    # Try to use the user's preferred editor
                    EDITOR="${SUDO_EDITOR:-${EDITOR:-nano}}"
                    $EDITOR "$ENV_FILE"
                fi
            else
                error "Service requires mqtt.env file - create it manually"
                exit 1
            fi
        else
            error "Template not found: $ENV_EXAMPLE"
            error "Cannot proceed without environment configuration"
            exit 1
        fi
    else
        info "Environment file exists: $ENV_FILE"

        # Validate required variables
        if ! grep -q "^MQTT_SERVER=" "$ENV_FILE"; then
            warn "MQTT_SERVER not set in $ENV_FILE"
        fi
    fi

    # Ensure proper permissions
    chmod 600 "$ENV_FILE"
    info "Environment file permissions set to 600 (secure)"
}

# Remove old cron job if it exists
remove_cron() {
    info "Checking for existing cron jobs..."

    # Detect the user from the service file
    SERVICE_USER=$(grep "^User=" "$SOURCE_SERVICE" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    SERVICE_USER=${SERVICE_USER:-weather}

    # Check user's crontab
    if sudo -u "$SERVICE_USER" crontab -l 2>/dev/null | grep -q "mqtt.py\|weatherhat"; then
        warn "Found existing cron entry for weather station"
        echo ""
        echo "Current cron entries:"
        sudo -u "$SERVICE_USER" crontab -l 2>/dev/null | grep -E "mqtt|weather" || true
        echo ""

        read -p "Remove cron entries? [y/N] " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Remove lines containing mqtt.py or weatherhat from crontab
            sudo -u "$SERVICE_USER" crontab -l 2>/dev/null | grep -v -E "mqtt\.py|weatherhat" | sudo -u "$SERVICE_USER" crontab - || true
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
    echo "Configuration file: $ENV_FILE"
    echo ""
    echo "Useful commands:"
    echo ""
    echo "  # Edit configuration"
    echo "  nano $ENV_FILE"
    echo "  sudo systemctl restart $SERVICE_NAME  # after editing"
    echo ""
    echo "  # Check service status"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo ""
    echo "  # View live logs (structured logging)"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "  # View recent logs with errors only"
    echo "  sudo journalctl -u $SERVICE_NAME -p err -n 50"
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
    echo "Performance monitoring:"
    echo "  # Check CPU/Memory usage"
    echo "  top -p \$(pgrep -f mqtt.py)"
    echo ""
    echo "  # Monitor MQTT data"
    echo "  mosquitto_sub -h YOUR_MQTT_SERVER -t 'sensors/#' -v"
    echo ""
}

# Main
main() {
    setup_environment
    echo ""
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
