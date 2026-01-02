#!/bin/bash
# install-dependencies.sh
# Weather HAT dependency installer for Raspberry Pi Zero WH (ARMv6)
# Handles architecture limitations by preferring system packages

set -e

echo "=========================================="
echo "Weather HAT Dependency Installer"
echo "Optimized for Pi Zero WH (ARMv6)"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running on Pi Zero
check_architecture() {
    ARCH=$(uname -m)
    info "Detected architecture: $ARCH"
    
    if [ "$ARCH" = "armv6l" ]; then
        info "Pi Zero (ARMv6) detected - using compatible installation method"
        IS_ARMV6=true
    else
        info "Non-ARMv6 architecture - standard installation will be used"
        IS_ARMV6=false
    fi
}

# Update system packages
update_system() {
    info "Updating package lists..."
    sudo apt-get update
}

# Install system-level dependencies (avoids pip compilation issues on ARMv6)
install_system_packages() {
    info "Installing system packages..."
    
    # Core Python packages - using system versions avoids ARMv6 compilation failures
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
        python3-lgpio \
    
    # Install correct libgpiod version (2 for older Bookworm, 3 for newer)
    if apt-cache show libgpiod3 &>/dev/null; then
        sudo apt-get install -y libgpiod3 python3-libgpiod
    else
        sudo apt-get install -y libgpiod2 python3-libgpiod
    fi
    
    # Optional: fonts for display
    sudo apt-get install -y fonts-dejavu || warn "Font package not critical"
}

# Enable required interfaces
enable_interfaces() {
    info "Enabling I2C and SPI interfaces..."
    
    # Enable I2C
    if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null && \
       ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
        warn "I2C may not be enabled. Run: sudo raspi-config"
    fi
    
    # Enable SPI
    if ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null && \
       ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
        warn "SPI may not be enabled. Run: sudo raspi-config"
    fi
    
    # Add user to required groups
    sudo usermod -aG i2c,spi,gpio $USER 2>/dev/null || true
}

# Create virtual environment with system packages access
setup_virtualenv() {
    VENV_PATH="$HOME/.virtualenvs/pimoroni"
    
    info "Setting up virtual environment at $VENV_PATH..."
    
    # Create venv with access to system packages (critical for ARMv6)
    if [ ! -d "$VENV_PATH" ]; then
        python3 -m venv --system-site-packages "$VENV_PATH"
        info "Virtual environment created"
    else
        info "Virtual environment already exists"
    fi
    
    # Activate venv
    source "$VENV_PATH/bin/activate"
    
    # Upgrade pip within venv
    pip install --upgrade pip wheel setuptools
}

# Install Python packages in virtual environment
install_python_packages() {
    VENV_PATH="$HOME/.virtualenvs/pimoroni"
    source "$VENV_PATH/bin/activate"
    
    info "Installing Python packages in virtual environment..."
    
    if [ "$IS_ARMV6" = true ]; then
        # ARMv6: Install only packages that have wheels or are pure Python
        # System packages provide: smbus, gpiozero, paho-mqtt, numpy, PIL
        
        # Pimoroni packages - pure Python, should work
        pip install --upgrade \
            fonts \
            font-dejavu \
            st7789 \
            pimoroni-bme280 \
            ltr559 \
            ads1015 \
            || warn "Some Pimoroni packages may have failed"
        
        # Install weatherhat from local fork
        if [ -d "$HOME/weatherhat-python" ]; then

            # Fix missing CHANGELOG.md issue with hatch build system
            cd "$HOME/weatherhat-python"
            if [ ! -f "CHANGELOG.md" ]; then
                info "Creating dummy CHANGELOG.md to satisfy build requirements..."
                echo "# Changelog" > CHANGELOG.md
                echo "" >> CHANGELOG.md
                echo "## Local fork" >> CHANGELOG.md
                echo "Modified for local MQTT publishing." >> CHANGELOG.md
            fi

            info "Installing weatherhat from local repository..."
            pip install -e "$HOME/weatherhat-python"
        else
            warn "weatherhat-python not found at $HOME/weatherhat-python"
            warn "Clone your fork: git clone https://github.com/timFinn/weatherhat-python.git"
        fi
    else
        # Non-ARMv6: Standard installation
        pip install --upgrade \
            paho-mqtt \
            gpiozero \
            RPi.GPIO \
            smbus \
            fonts \
            font-dejavu \
            st7789 \
            pimoroni-bme280 \
            ltr559 \
            ads1015
        
        if [ -d "$HOME/weatherhat-python" ]; then
            pip install -e "$HOME/weatherhat-python"
        fi
    fi
}

# Verify installation
verify_installation() {
    VENV_PATH="$HOME/.virtualenvs/pimoroni"
    source "$VENV_PATH/bin/activate"
    
    info "Verifying installation..."
    
    echo ""
    echo "Testing imports..."
    
    python3 << 'EOF'
import sys
errors = []

modules = [
    ('paho.mqtt.client', 'paho-mqtt'),
    ('smbus', 'smbus/smbus2'),
    ('gpiozero', 'gpiozero'),
    ('weatherhat', 'weatherhat'),
]

for module, name in modules:
    try:
        __import__(module)
        print(f"  ✓ {name}")
    except ImportError as e:
        print(f"  ✗ {name}: {e}")
        errors.append(name)

if errors:
    print(f"\nSome modules failed to import: {errors}")
    sys.exit(1)
else:
    print("\nAll core modules imported successfully!")
EOF
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
    echo "  2. Test manually: source ~/.virtualenvs/pimoroni/bin/activate && python mqtt.py"
    echo "  3. Install systemd service: sudo ./install-service.sh"
    echo ""
}

main "$@"
