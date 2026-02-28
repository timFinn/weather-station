#!/bin/bash
# update.sh
# Pulls latest code and restarts the weatherhat service

set -e

SERVICE_NAME="weatherhat"
SERVICE_USER="weather"
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

echo "=========================================="
echo "Weather HAT Update"
echo "=========================================="
echo ""

# Pull latest code
info "Pulling latest code..."
sudo -u "$(stat -c '%U' "$SOURCE_PROJECT/.git")" git -C "$SOURCE_PROJECT" pull --ff-only
echo ""

# Snapshot requirements.txt before sync
OLD_REQS=""
if [ -f "$TARGET_PROJECT/requirements.txt" ]; then
    OLD_REQS=$(cat "$TARGET_PROJECT/requirements.txt")
fi

# Sync to deployment target
if [ "$SOURCE_PROJECT" = "$TARGET_PROJECT" ]; then
    info "Already running from target location"
else
    info "Syncing to $TARGET_PROJECT..."
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='config/mqtt.env' \
        "$SOURCE_PROJECT/" "$TARGET_PROJECT/"

    info "Setting ownership to $SERVICE_USER..."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$TARGET_PROJECT"
fi
echo ""

# Update pip dependencies if requirements.txt changed
NEW_REQS=$(cat "$TARGET_PROJECT/requirements.txt")
if [ "$OLD_REQS" != "$NEW_REQS" ]; then
    info "requirements.txt changed, updating dependencies..."
    sudo -u "$SERVICE_USER" "$VENV_PATH/bin/pip" install -r "$TARGET_PROJECT/requirements.txt"
    echo ""
else
    info "requirements.txt unchanged, skipping pip install"
fi

# Reload service file if it changed
if ! diff -q "$SOURCE_SERVICE" /etc/systemd/system/weatherhat.service &>/dev/null; then
    info "Service file changed, updating..."
    cp "$SOURCE_SERVICE" /etc/systemd/system/weatherhat.service
    chmod 644 /etc/systemd/system/weatherhat.service
    systemctl daemon-reload
else
    info "Service file unchanged"
fi

# Restart service
info "Restarting $SERVICE_NAME..."
systemctl restart "$SERVICE_NAME"
sleep 3

info "Service status:"
systemctl status "$SERVICE_NAME" --no-pager -l || true
echo ""
info "Update complete"
