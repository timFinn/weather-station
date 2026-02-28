#!/bin/bash
# test-mqtt.sh
# Diagnostic script for MQTT connectivity issues
# Run on the Pi to check broker status and test publishing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PROJECT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# Load env file if available
ENV_FILE="$SOURCE_PROJECT/config/mqtt.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    info "Loaded config from $ENV_FILE"
else
    warn "No mqtt.env found, using defaults"
fi

MQTT_SERVER="${MQTT_SERVER:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USERNAME="${MQTT_USERNAME:-}"
MQTT_PASSWORD="${MQTT_PASSWORD:-}"
MQTT_CLIENT_ID="${MQTT_CLIENT_ID:-weatherhat}"
MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX:-sensors}"

# Build auth flags
AUTH_FLAGS=""
if [ -n "$MQTT_USERNAME" ]; then
    AUTH_FLAGS="-u $MQTT_USERNAME"
    if [ -n "$MQTT_PASSWORD" ]; then
        AUTH_FLAGS="$AUTH_FLAGS -P $MQTT_PASSWORD"
    fi
fi

echo "=========================================="
echo "MQTT Diagnostics"
echo "=========================================="
echo ""
echo "Broker: $MQTT_SERVER:$MQTT_PORT"
echo "Client ID: $MQTT_CLIENT_ID"
echo "Topic prefix: $MQTT_TOPIC_PREFIX"
echo ""

# Check mosquitto clients are installed
if ! command -v mosquitto_sub &>/dev/null; then
    error "mosquitto-clients not installed. Run: sudo apt install mosquitto-clients"
    exit 1
fi

# Test 1: TCP connectivity
echo "------------------------------------------"
info "Test 1: TCP connectivity to $MQTT_SERVER:$MQTT_PORT"
if timeout 5 bash -c "echo > /dev/tcp/$MQTT_SERVER/$MQTT_PORT" 2>/dev/null; then
    pass "TCP connection successful"
else
    fail "Cannot reach $MQTT_SERVER:$MQTT_PORT"
    exit 1
fi
echo ""

# Test 2: MQTT connect with a unique test client ID
echo "------------------------------------------"
info "Test 2: MQTT broker authentication"
TEST_CLIENT_ID="diag-test-$$"
if timeout 5 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$TEST_CLIENT_ID" -t "test/diag" -C 0 -W 2 2>&1; then
    pass "MQTT authentication successful"
else
    # mosquitto_sub returns non-zero on timeout which is expected here
    pass "MQTT broker accepted connection"
fi
echo ""

# Test 3: Check for client ID conflicts
echo "------------------------------------------"
info "Test 3: Client ID conflict check for '$MQTT_CLIENT_ID'"
info "Subscribing as '$MQTT_CLIENT_ID' for 5 seconds — watch for disconnects..."
echo ""
timeout 5 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$MQTT_CLIENT_ID" -t "test/conflict-check" -v -W 5 2>&1
SUB_EXIT=$?
if [ $SUB_EXIT -eq 0 ] || [ $SUB_EXIT -eq 27 ]; then
    # 0 = message received and exited, 27 = timed out (expected)
    pass "No client ID conflict detected (held connection for 5s)"
else
    fail "Connection was interrupted — another client may be using ID '$MQTT_CLIENT_ID'"
    warn "Check your broker for duplicate client IDs or set a unique MQTT_CLIENT_ID in mqtt.env"
fi
echo ""

# Test 4: Publish and subscribe round-trip
echo "------------------------------------------"
info "Test 4: Publish/subscribe round-trip"
TEST_TOPIC="$MQTT_TOPIC_PREFIX/test/diag"
TEST_PAYLOAD="diag-$(date +%s)"
SUB_CLIENT="diag-sub-$$"
PUB_CLIENT="diag-pub-$$"

# Start subscriber in background
mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$SUB_CLIENT" -t "$TEST_TOPIC" -C 1 -W 5 > /tmp/mqtt_diag_result 2>&1 &
SUB_PID=$!
sleep 1

# Publish test message
mosquitto_pub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$PUB_CLIENT" -t "$TEST_TOPIC" -m "$TEST_PAYLOAD" 2>&1

# Wait for subscriber
wait $SUB_PID 2>/dev/null || true
RECEIVED=$(cat /tmp/mqtt_diag_result 2>/dev/null)
rm -f /tmp/mqtt_diag_result

if [ "$RECEIVED" = "$TEST_PAYLOAD" ]; then
    pass "Round-trip successful: published and received '$TEST_PAYLOAD'"
else
    fail "Round-trip failed: expected '$TEST_PAYLOAD', got '$RECEIVED'"
fi
echo ""

# Test 5: Check broker $SYS topics for connected clients
echo "------------------------------------------"
info "Test 5: Broker stats (if $SYS topics available)"
SYS_OUTPUT=$(timeout 3 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "diag-sys-$$" -t '$SYS/broker/clients/connected' -C 1 -W 3 2>/dev/null || true)
if [ -n "$SYS_OUTPUT" ]; then
    info "Connected clients: $SYS_OUTPUT"
else
    warn "\$SYS topics not available (broker may have them disabled)"
fi
echo ""

echo "=========================================="
info "Diagnostics complete"
echo "=========================================="
