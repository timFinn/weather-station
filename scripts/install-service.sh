#!/bin/bash
# install-service.sh
# Installs the Weather HAT systemd service with full user and environment setup

set -e

SERVICE_NAME="weatherhat"
SERVICE_USER="weather"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PROJECT="$(dirname "$SCRIPT_DIR")"
TARGET_PROJECT="/home/$SERVICE_USER/weather-station"
SOURCE_SERVICE="$SOURCE_PROJECT/weatherhat.service"
VENV_PATH="/home/$SERVICE_USER/.virtualenvs/pimoroni"

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
echo "Weather HAT Service Installer"
echo "=========================================="
echo ""
info "Source project: $SOURCE_PROJECT"
info "Target project: $TARGET_PROJECT"
info "Service user: $SERVICE_USER"
echo ""

# Create service user if needed
setup_user() {
    info "Checking service user..."

    if id "$SERVICE_USER" &>/dev/null; then
        info "User '$SERVICE_USER' already exists"
    else
        info "Creating user '$SERVICE_USER'..."
        useradd --create-home --shell /bin/bash "$SERVICE_USER"
        info "User '$SERVICE_USER' created"
    fi

    # Add user to required hardware groups
    local groups_to_add=""
    for group in i2c gpio spi; do
        if getent group "$group" &>/dev/null; then
            if ! id -nG "$SERVICE_USER" | grep -qw "$group"; then
                groups_to_add="$groups_to_add,$group"
            fi
        else
            warn "Group '$group' does not exist - may need to enable interface"
        fi
    done

    if [ -n "$groups_to_add" ]; then
        groups_to_add="${groups_to_add:1}"  # Remove leading comma
        info "Adding '$SERVICE_USER' to groups: $groups_to_add"
        usermod -aG "$groups_to_add" "$SERVICE_USER"
    else
        info "User already in required groups"
    fi
}

# Set up project in target location
setup_project() {
    info "Setting up project files..."

    if [ "$SOURCE_PROJECT" = "$TARGET_PROJECT" ]; then
        info "Already running from target location"
    elif [ -d "$TARGET_PROJECT" ]; then
        info "Target directory exists, updating files..."
        rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
            "$SOURCE_PROJECT/" "$TARGET_PROJECT/"
    else
        info "Copying project to $TARGET_PROJECT..."
        mkdir -p "$TARGET_PROJECT"
        rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
            "$SOURCE_PROJECT/" "$TARGET_PROJECT/"
    fi

    # Set ownership
    info "Setting ownership to $SERVICE_USER..."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$TARGET_PROJECT"
}

# Set up Python virtual environment
setup_virtualenv() {
    info "Checking Python virtual environment..."

    if [ -d "$VENV_PATH" ]; then
        info "Virtual environment exists at $VENV_PATH"
    else
        info "Creating virtual environment..."
        sudo -u "$SERVICE_USER" python3 -m venv --system-site-packages "$VENV_PATH"
        info "Virtual environment created"
    fi

    # Install/upgrade dependencies
    info "Installing Python dependencies..."
    sudo -u "$SERVICE_USER" "$VENV_PATH/bin/pip" install --upgrade pip
    sudo -u "$SERVICE_USER" "$VENV_PATH/bin/pip" install -r "$TARGET_PROJECT/requirements.txt"
    info "Dependencies installed"

    # Install local weatherhat package (contains ha_discovery, i2c_recovery, etc.
    # that aren't in the upstream PyPI release)
    info "Installing local weatherhat package..."
    sudo -u "$SERVICE_USER" "$VENV_PATH/bin/pip" install --no-deps "$TARGET_PROJECT"
    info "weatherhat package installed"
}

# Check and setup environment file
setup_environment() {
    info "Checking environment configuration..."

    local env_example="$TARGET_PROJECT/config/mqtt.env.example"
    local env_file="$TARGET_PROJECT/config/mqtt.env"

    if [ ! -f "$env_file" ]; then
        warn "Environment file not found: $env_file"

        if [ -f "$env_example" ]; then
            echo ""
            prompt "Would you like to create it from the example template?"
            read -p "Create mqtt.env? [Y/n] " -n 1 -r
            echo ""

            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                cp "$env_example" "$env_file"
                chmod 600 "$env_file"
                chown "$SERVICE_USER:$SERVICE_USER" "$env_file"
                info "Created $env_file from template"
                echo ""
                warn "⚠️  IMPORTANT: You must edit $env_file before starting the service!"
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
                    EDITOR="${SUDO_EDITOR:-${EDITOR:-nano}}"
                    $EDITOR "$env_file"
                fi
            else
                error "Service requires mqtt.env file - create it manually"
                exit 1
            fi
        else
            error "Template not found: $env_example"
            exit 1
        fi
    else
        info "Environment file exists: $env_file"

        if ! grep -q "^MQTT_SERVER=" "$env_file"; then
            warn "MQTT_SERVER not set in $env_file"
        fi
    fi

    # Ensure proper permissions and ownership
    chmod 600 "$env_file"
    chown "$SERVICE_USER:$SERVICE_USER" "$env_file"
    info "Environment file secured"
}

# Install sudoers rule for I2C bus recovery
setup_sudoers() {
    info "Checking sudoers for I2C recovery..."

    local sudoers_file="/etc/sudoers.d/weatherhat-i2c-recovery"
    local recovery_script="$TARGET_PROJECT/scripts/i2c-bus-recovery.sh"
    local expected="$SERVICE_USER ALL=(root) NOPASSWD: $recovery_script"

    if [ -f "$sudoers_file" ] && grep -qF "$recovery_script" "$sudoers_file"; then
        info "Sudoers rule already in place"
    else
        info "Installing sudoers rule for I2C bus recovery..."
        echo "$expected" > "$sudoers_file"
        chmod 440 "$sudoers_file"
        # Validate syntax before leaving it in place
        if visudo -cf "$sudoers_file" &>/dev/null; then
            info "Sudoers rule installed: $sudoers_file"
        else
            rm -f "$sudoers_file"
            error "Sudoers syntax check failed, removed $sudoers_file"
        fi
    fi
}

# Remove old cron job if it exists
remove_cron() {
    info "Checking for existing cron jobs..."

    if sudo -u "$SERVICE_USER" crontab -l 2>/dev/null | grep -q "mqtt.py\|weatherhat"; then
        warn "Found existing cron entry for weather station"
        echo ""
        sudo -u "$SERVICE_USER" crontab -l 2>/dev/null | grep -E "mqtt|weather" || true
        echo ""

        read -p "Remove cron entries? [y/N] " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
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
    echo "Service user: $SERVICE_USER"
    echo "Project location: $TARGET_PROJECT"
    echo "Virtual environment: $VENV_PATH"
    echo "Configuration: $TARGET_PROJECT/config/mqtt.env"
    echo ""
    echo "Useful commands:"
    echo ""
    echo "  # Check service status"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo ""
    echo "  # View live logs"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "  # Edit configuration"
    echo "  sudo nano $TARGET_PROJECT/config/mqtt.env"
    echo "  sudo systemctl restart $SERVICE_NAME"
    echo ""
    echo "  # Restart / stop service"
    echo "  sudo systemctl restart $SERVICE_NAME"
    echo "  sudo systemctl stop $SERVICE_NAME"
    echo ""
    echo "  # Run manually as $SERVICE_USER"
    echo "  sudo -u $SERVICE_USER $VENV_PATH/bin/python $TARGET_PROJECT/bin/mqtt-publisher.py"
    echo ""
}

# Main
main() {
    setup_user
    echo ""
    setup_project
    echo ""
    setup_virtualenv
    echo ""
    setup_environment
    echo ""
    setup_sudoers
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
