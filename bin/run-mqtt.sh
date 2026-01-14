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
