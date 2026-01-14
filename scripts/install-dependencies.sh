#!/bin/bash
# install-dependencies.sh
# Weather HAT dependency installer
# Supports Pi Zero 2 W (aarch64) and Pi Zero WH (armv6l)

set -e

echo "=========================================="
echo "Weather HAT Dependency Installer"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check architecture
check_architecture() {
    ARCH=$(uname -m)
    info "Detected architecture: $ARCH"
    
    case "$ARCH" in
        aarch64)
            info "64-bit detected - full package compatibility"
            IS_64BIT=true
            ;;
        armv7l)
            info "ARMv7 (32-bit) detected - good package compatibility"
            IS_64BIT=false
            ;;
        armv6l)
            warn "Pi Zero (ARMv6) detected - using compatible installation method"
            IS_64BIT=false
            ;;
        *)
            warn "Unknown architecture: $ARCH"
            IS_64BIT=false
            ;;
    esac
}

# Update system packages
update_system() {
    info "Updating package lists..."
    sudo apt-get update
}

# Install system-level dependencies
install_system_packages() {
    info "Installing system packages..."
    
    # Core Python packages
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-smbus \
        python3-paho-mqtt \
        python3-gpiozero \
        python3-rpi.gpio \
        python3-spidev \
        python3-pil \
        python3-numpy
    
    # I2C and SPI tools
    sudo apt-get install -y \
        i2c-tools \
        python3-lgpio
    
    # Handle libgpiod version differences (libgpiod2 vs libgpiod3)
    info "Detecting libgpiod version..."
    if apt-cache show libgpiod3 &>/dev/null; then
        info "Installing libgpiod3 (newer Bookworm)"
        sudo apt-get install -y libgpiod3 python3-libgpiod
    elif apt-cache show libgpiod2 &>/dev/null; then
        info "Installing libgpiod2 (older Bookworm)"
        sudo apt-get install -y libgpiod2 python3-libgpiod
    else
        warn "No libgpiod package found - installing python3-libgpiod only"
        sudo apt-get install -y python3-libgpiod || warn "python3-libgpiod not available"
    fi
    
    # Optional: fonts for display
    sudo apt-get install -y fonts-dejavu || warn "Font package not critical"
}

# Enable required interfaces
enable_interfaces() {
    info "Checking I2C and SPI interfaces..."
    
    # Check for config in either location (Pi 4/5 vs older)
    CONFIG_FILE=""
    if [ -f /boot/firmware/config.txt ]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    elif [ -f /boot/config.txt ]; then
        CONFIG_FILE="/boot/config.txt"
    fi
    
    if [ -n "$CONFIG_FILE" ]; then
        if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE"; then
            warn "I2C may not be enabled. Run: sudo raspi-config"
        else
            info "I2C is enabled"
        fi
        
        if ! grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
            warn "SPI may not be enabled. Run: sudo raspi-config"
        else
            info "SPI is enabled"
        fi
    else
        warn "Could not find config.txt - verify I2C/SPI manually"
    fi
}

# Setup Python virtual environment
setup_virtualenv() {
    VENV_PATH="$HOME/.virtualenvs/pimoroni"
    
    info "Setting up virtual environment at $VENV_PATH..."
    
    # Create virtualenvs directory if needed
    mkdir -p "$HOME/.virtualenvs"
    
    # Remove broken venv if it exists
    if [ -d "$VENV_PATH" ] && [ ! -f "$VENV_PATH/bin/python" ]; then
        warn "Removing broken virtualenv..."
        rm -rf "$VENV_PATH"
    fi
    
    # Create venv with system site packages (gives us pre-built packages)
    if [ ! -d "$VENV_PATH" ]; then
        python3 -m venv --system-site-packages "$VENV_PATH"
        info "Virtual environment created"
    else
        info "Virtual environment already exists"
    fi
    
    # Activate and upgrade pip
    source "$VENV_PATH/bin/activate"
    pip install --upgrade pip wheel
}

# Install Python packages
install_python_packages() {
    info "Installing Python packages in virtualenv..."
    
    source "$HOME/.virtualenvs/pimoroni/bin/activate"
    
    # Install/upgrade packages that work well from pip
    pip install --upgrade \
        smbus2 \
        fonts \
        font-roboto \
        st7789
    
    # Install weatherhat from local repo if present
    if [ -d "$HOME/weatherhat-python" ]; then
        info "Installing weatherhat from local repository..."
        
        # Create CHANGELOG.md if missing (required by build system)
        if [ ! -f "$HOME/weatherhat-python/CHANGELOG.md" ]; then
            cat > "$HOME/weatherhat-python/CHANGELOG.md" << 'EOF'
# Changelog

## Local fork
Modified for local MQTT publishing to Mosquitto broker.
EOF
            info "Created missing CHANGELOG.md"
        fi
        
        pip install -e "$HOME/weatherhat-python"
    else
        warn "weatherhat-python not found at ~/weatherhat-python"
        warn "Clone it first: git clone https://github.com/pimoroni/weatherhat-python"
    fi
}

# Verify installation
verify_installation() {
    info "Verifying installation..."
    
    source "$HOME/.virtualenvs/pimoroni/bin/activate"
    
    echo ""
    echo "Python path: $(which python)"
    echo "Python version: $(python --version)"
    echo ""
    
    # Test critical imports
    FAILED=false
    
    for module in smbus2 gpiozero paho.mqtt.client PIL numpy; do
        if python -c "import $module" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $module"
        else
            echo -e "  ${RED}✗${NC} $module"
            FAILED=true
        fi
    done
    
    # Test weatherhat separately (may not be installed yet)
    if python -c "import weatherhat" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} weatherhat"
    else
        echo -e "  ${YELLOW}?${NC} weatherhat (install from ~/weatherhat-python)"
    fi
    
    echo ""
    
    if [ "$FAILED" = true ]; then
        error "Some packages failed to import - check errors above"
        return 1
    else
        info "All critical packages verified!"
    fi
}

# Test hardware connectivity
test_hardware() {
    info "Testing hardware connectivity..."
    
    echo ""
    echo "I2C devices detected:"
    i2cdetect -y 1 2>/dev/null || warn "I2C detection failed - ensure I2C is enabled"
    
    echo ""
    info "Expected addresses for Weather HAT:"
    echo "  0x76 or 0x77 - BME280 (temperature/humidity/pressure)"
    echo "  0x23 - LTR559 (light sensor)"
    echo "  0x48 - ADS1015 (ADC for wind/rain)"
}

# Main installation flow
main() {
    echo ""
    check_architecture
    echo ""
    
    update_system
    echo ""
    
    install_system_packages
    echo ""
    
    enable_interfaces
    echo ""
    
    setup_virtualenv
    echo ""
    
    install_python_packages
    echo ""
    
    verify_installation
    echo ""
    
    test_hardware
    echo ""
    
    echo "=========================================="
    info "Installation complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Reboot if this is a fresh install: sudo reboot"
    echo "  2. Test manually:"
    echo "     source ~/.virtualenvs/pimoroni/bin/activate"
    echo "     python ~/weatherhat-python/bin/mqtt-publisher.py"
    echo "  3. Install systemd service: sudo ./install-service.sh"
    echo ""
}

main "$@"