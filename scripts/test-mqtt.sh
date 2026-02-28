#!/bin/bash
# test-mqtt.sh
# Diagnostic script for MQTT connectivity issues
# Run on the Pi to check broker status and test publishing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PROJECT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
echo "Broker:       $MQTT_SERVER:$MQTT_PORT"
echo "Client ID:    $MQTT_CLIENT_ID"
echo "Topic prefix: $MQTT_TOPIC_PREFIX"
echo "Auth:         $([ -n "$MQTT_USERNAME" ] && echo "yes ($MQTT_USERNAME)" || echo "none")"
echo ""

# Check mosquitto clients are installed
if ! command -v mosquitto_sub &>/dev/null; then
    error "mosquitto-clients not installed. Run: sudo apt install mosquitto-clients"
    exit 1
fi

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: DNS resolution
echo "------------------------------------------"
info "Test 1: DNS resolution for $MQTT_SERVER"
if [[ "$MQTT_SERVER" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    pass "Using IP address directly"
    TESTS_PASSED=$((TESTS_PASSED + 1))
elif RESOLVED_IP=$(getent hosts "$MQTT_SERVER" 2>/dev/null | awk '{print $1}'); [ -n "$RESOLVED_IP" ]; then
    pass "DNS resolved: $MQTT_SERVER -> $RESOLVED_IP"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Cannot resolve $MQTT_SERVER"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# Test 2: TCP connectivity
echo "------------------------------------------"
info "Test 2: TCP connectivity to $MQTT_SERVER:$MQTT_PORT"
if timeout 5 bash -c "echo > /dev/tcp/$MQTT_SERVER/$MQTT_PORT" 2>/dev/null; then
    pass "TCP connection successful"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Cannot reach $MQTT_SERVER:$MQTT_PORT"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    error "Remaining tests require connectivity — aborting"
    exit 1
fi
echo ""

# Test 3: MQTT connect with a unique test client ID
echo "------------------------------------------"
info "Test 3: MQTT broker authentication"
TEST_CLIENT_ID="diag-auth-$$"
AUTH_OUTPUT=$(timeout 5 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$TEST_CLIENT_ID" -t "test/diag" -W 2 -E 2>&1) || true
if echo "$AUTH_OUTPUT" | grep -qi "not authorized\|bad user\|connection refused"; then
    fail "Authentication rejected: $AUTH_OUTPUT"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    pass "Broker accepted connection"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi
echo ""

# Test 4: Client ID conflict check
echo "------------------------------------------"
info "Test 4: Client ID conflict check for '$MQTT_CLIENT_ID'"
info "Holding connection as '$MQTT_CLIENT_ID' for 5 seconds..."

# Connect with the configured client ID and check if we get kicked
CONFLICT_OUTPUT=$(timeout 6 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "$MQTT_CLIENT_ID" -t "test/conflict-check" -W 5 -E 2>&1)
CONFLICT_EXIT=$?

if [ $CONFLICT_EXIT -eq 124 ] || [ $CONFLICT_EXIT -eq 0 ]; then
    # 124 = timeout killed it (good - held for full 5s), 0 = clean exit from -W
    pass "No conflict — held connection for 5 seconds"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Connection dropped (exit $CONFLICT_EXIT) — client ID '$MQTT_CLIENT_ID' is in use"
    if [ -n "$CONFLICT_OUTPUT" ]; then
        error "Output: $CONFLICT_OUTPUT"
    fi
    warn "Another client is connected with this ID. Change MQTT_CLIENT_ID in mqtt.env"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# Test 5: Publish and subscribe round-trip
echo "------------------------------------------"
info "Test 5: Publish/subscribe round-trip"
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
    -i "$PUB_CLIENT" -t "$TEST_TOPIC" -m "$TEST_PAYLOAD" 2>&1 || true

# Wait for subscriber
wait $SUB_PID 2>/dev/null || true
RECEIVED=$(cat /tmp/mqtt_diag_result 2>/dev/null)
rm -f /tmp/mqtt_diag_result

if [ "$RECEIVED" = "$TEST_PAYLOAD" ]; then
    pass "Round-trip OK: published and received '$TEST_PAYLOAD'"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Round-trip failed: expected '$TEST_PAYLOAD', got '${RECEIVED:-<empty>}'"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# Test 6: Broker stats
echo "------------------------------------------"
info "Test 6: Broker stats"
declare -A SYS_TOPICS=(
    ["clients/connected"]=""
    ["clients/total"]=""
    ["clients/maximum"]=""
)
for key in "${!SYS_TOPICS[@]}"; do
    val=$(timeout 3 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
        -i "diag-sys-$key-$$" -t "\$SYS/broker/$key" -C 1 -W 3 2>/dev/null || true)
    if [ -n "$val" ]; then
        SYS_TOPICS[$key]="$val"
    fi
done

if [ -n "${SYS_TOPICS[clients/connected]}" ]; then
    info "Connected:  ${SYS_TOPICS[clients/connected]}"
    info "Total:      ${SYS_TOPICS[clients/total]}"
    info "Maximum:    ${SYS_TOPICS[clients/maximum]}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    warn "\$SYS topics not available (broker may have them disabled)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi
echo ""

# Test 7: Check weatherhat service status
echo "------------------------------------------"
info "Test 7: Service status"
if systemctl is-active --quiet weatherhat 2>/dev/null; then
    pass "weatherhat service is running"
    SERVICE_PID=$(systemctl show weatherhat --property=MainPID --value 2>/dev/null)
    if [ -n "$SERVICE_PID" ] && [ "$SERVICE_PID" != "0" ]; then
        info "PID: $SERVICE_PID"
        # Check CPU and memory usage
        PS_OUTPUT=$(ps -p "$SERVICE_PID" -o %cpu,%mem,etime --no-headers 2>/dev/null || true)
        if [ -n "$PS_OUTPUT" ]; then
            info "CPU/MEM/Uptime: $PS_OUTPUT"
        fi
    fi
    TESTS_PASSED=$((TESTS_PASSED + 1))
elif systemctl is-enabled --quiet weatherhat 2>/dev/null; then
    fail "weatherhat service is stopped but enabled"
    warn "Recent logs:"
    journalctl -u weatherhat --no-pager -n 5 2>/dev/null || true
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    warn "weatherhat service not installed"
    TESTS_PASSED=$((TESTS_PASSED + 1))
fi
echo ""

# Test 8: Check for recent errors in journal
echo "------------------------------------------"
info "Test 8: Recent service errors (last 50 lines)"
ERROR_COUNT=$(journalctl -u weatherhat --no-pager -n 50 --since "5 min ago" 2>/dev/null \
    | grep -ci "error\|critical\|disconnect" || true)
RECONNECT_COUNT=$(journalctl -u weatherhat --no-pager -n 50 --since "5 min ago" 2>/dev/null \
    | grep -ci "reconnect\|retrying" || true)

if [ "$ERROR_COUNT" -eq 0 ] && [ "$RECONNECT_COUNT" -eq 0 ]; then
    pass "No errors or reconnects in last 5 minutes"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    if [ "$ERROR_COUNT" -gt 0 ]; then
        fail "$ERROR_COUNT error/critical/disconnect messages in last 5 minutes"
    fi
    if [ "$RECONNECT_COUNT" -gt 0 ]; then
        fail "$RECONNECT_COUNT reconnect attempts in last 5 minutes"
    fi
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo ""
    warn "Last 10 log lines:"
    journalctl -u weatherhat --no-pager -n 10 2>/dev/null || true
fi
echo ""

# Test 9: Check if data is flowing on expected topics
echo "------------------------------------------"
info "Test 9: Data flow check (listening for 10s on $MQTT_TOPIC_PREFIX/#)"
DATA_OUTPUT=$(timeout 10 mosquitto_sub -h "$MQTT_SERVER" -p "$MQTT_PORT" $AUTH_FLAGS \
    -i "diag-flow-$$" -t "$MQTT_TOPIC_PREFIX/#" -v -C 1 -W 10 2>&1) || true

if [ -n "$DATA_OUTPUT" ]; then
    pass "Received data: $(echo "$DATA_OUTPUT" | head -1)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "No data received on $MQTT_TOPIC_PREFIX/# within 10 seconds"
    warn "The publisher may not be connected or sensors may have failed"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# Summary
echo "=========================================="
if [ "$TESTS_FAILED" -eq 0 ]; then
    pass "All $TESTS_PASSED tests passed"
else
    fail "$TESTS_FAILED test(s) failed, $TESTS_PASSED passed"
fi
echo "=========================================="
