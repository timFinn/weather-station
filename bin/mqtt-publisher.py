#!/usr/bin/env python3
"""
MQTT Weather Station Publisher

Reads data from WeatherHAT and publishes to MQTT broker.
Configure via environment variables or config file.
"""
import json
import logging
import os
import platform
import signal
import subprocess
import sys
from time import monotonic, sleep

import paho.mqtt.client as mqtt
from gpiozero import CPUTemperature

import weatherhat
from weatherhat.ha_discovery import publish_discovery_configs
from weatherhat.i2c_recovery import attempt_i2c_recovery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables with defaults
MQTT_SERVER = os.getenv("MQTT_SERVER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")  # Optional
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")  # Optional
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", f"weatherhat-{platform.node()}")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")

# Home Assistant MQTT Discovery (default: enabled, set HA_DISCOVERY=false to disable)
HA_DISCOVERY = os.getenv("HA_DISCOVERY", "true").lower() != "false"

# Sensor configuration
TEMP_OFFSET = float(os.getenv("TEMP_OFFSET", "-7.5"))
UPDATE_INTERVAL = float(os.getenv("UPDATE_INTERVAL", "2.0"))
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "5.0"))

# Retry configuration
MAX_RECONNECT_DELAY = 300  # 5 minutes max
INITIAL_RECONNECT_DELAY = 1

# Topic definitions
TOPICS = {
    'cpu_temp': f"{MQTT_TOPIC_PREFIX}/pi/cpu_temp",
    'temperature': f"{MQTT_TOPIC_PREFIX}/weather/temperature",
    'humidity': f"{MQTT_TOPIC_PREFIX}/weather/humidity",
    'relative_humidity': f"{MQTT_TOPIC_PREFIX}/weather/relative_humidity",
    'pressure': f"{MQTT_TOPIC_PREFIX}/weather/pressure",
    'dewpoint': f"{MQTT_TOPIC_PREFIX}/weather/dewpoint",
    'light': f"{MQTT_TOPIC_PREFIX}/weather/light",
    'wind_direction': f"{MQTT_TOPIC_PREFIX}/weather/wind_direction",
    'wind_speed': f"{MQTT_TOPIC_PREFIX}/weather/wind_speed",
    'rain': f"{MQTT_TOPIC_PREFIX}/weather/rain",
    'rain_total': f"{MQTT_TOPIC_PREFIX}/weather/rain_total",
    'throttled': f"{MQTT_TOPIC_PREFIX}/pi/throttled",
    'undervoltage': f"{MQTT_TOPIC_PREFIX}/pi/undervoltage",
    'undervoltage_now': f"{MQTT_TOPIC_PREFIX}/pi/undervoltage_now",
    'status': f"{MQTT_TOPIC_PREFIX}/weather/status",
}

# Sensor error threshold - exit after this many consecutive I2C failures
# to allow systemd to restart the process with a fresh connection
MAX_CONSECUTIVE_SENSOR_ERRORS = 5

# Attempt I2C bus recovery after this many consecutive errors (before giving up)
I2C_RECOVERY_THRESHOLD = 3

# Timeout for sensor reads - if an I2C call hangs longer than this,
# we treat it as a sensor error so we can still reach the error threshold
SENSOR_READ_TIMEOUT = 30  # seconds


class SensorTimeout(Exception):
    """Raised when a sensor read exceeds SENSOR_READ_TIMEOUT."""
    pass


def _timeout_handler(signum, frame):
    raise SensorTimeout(f"Sensor read timed out after {SENSOR_READ_TIMEOUT}s")

# Global state
sensor = None
cpu = None
mqtt_client = None
running = True
reconnect_delay = INITIAL_RECONNECT_DELAY
consecutive_sensor_errors = 0
last_successful_publish = monotonic()
service_start_time = monotonic()


#  Function Definitions

def signal_handler(sig, frame):
    """Handle graceful shutdown on SIGINT/SIGTERM"""
    global running
    logger.info("Shutdown signal received, cleaning up...")
    running = False


def on_connect(client, userdata, flags, rc):
    """Callback when MQTT connection is established"""
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_SERVER}:{MQTT_PORT} (client_id={MQTT_CLIENT_ID})")
        # Publish online status (retained so new subscribers see current state)
        client.publish(TOPICS['status'], payload="online", qos=1, retain=True)
        if HA_DISCOVERY:
            publish_discovery_configs(client, MQTT_TOPIC_PREFIX, MQTT_CLIENT_ID)
    else:
        error_messages = {
            1: "Incorrect protocol version",
            2: "Invalid client identifier",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized"
        }
        logger.error(f"Connection failed: {error_messages.get(rc, f'Unknown error {rc}')}")


def on_disconnect(client, userdata, rc):
    """Callback when MQTT connection is lost"""
    if rc != 0:
        logger.warning(f"Unexpected disconnect from MQTT broker (code: {rc})")


def on_message(client, userdata, msg):
    """Callback for incoming MQTT messages"""
    logger.debug(f"Received: {msg.topic} = {msg.payload.decode()}")


def on_publish(client, userdata, mid):
    """Callback when message is published (optional, for QoS > 0)"""
    logger.debug(f"Message {mid} published")


def send_payload(client, topic, data):
    """
    Publish sensor data to MQTT topic.

    Args:
        client: MQTT client instance
        topic: Topic to publish to
        data: Data value (will be JSON encoded)

    Returns:
        bool: True if publish succeeded, False otherwise
    """
    try:
        # Use original format for Telegraf compatibility: {topic: value}
        payload = json.dumps({topic: data})
        # Retain so new subscribers (e.g. the display service) get the latest
        # value on connect instead of waiting up to PUBLISH_INTERVAL.
        result = client.publish(topic=topic, payload=payload, qos=1, retain=True)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Publish failed for {topic}: {result.rc}")
            return False
        return True
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to encode payload for {topic}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing to {topic}: {e}")
        return False

def scan_i2c_devices():
    """Quick I2C bus scan to see which devices are responding."""
    try:
        result = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
        return f"i2cdetect failed (exit {result.returncode}): {result.stderr.strip()}"
    except FileNotFoundError:
        return "i2cdetect not installed"
    except subprocess.TimeoutExpired:
        return "i2cdetect timed out (bus may be hung)"
    except Exception as e:
        return f"i2cdetect error: {e}"


def log_sensor_diagnostics(error, error_count):
    """Log detailed system state when sensor errors occur.

    Captures throttle status, I2C bus state, and timing info to help
    diagnose intermittent failures after the fact.
    """
    now = monotonic()
    uptime = now - service_start_time
    time_since_success = now - last_successful_publish

    logger.warning(
        f"--- Sensor error diagnostics (error {error_count}/{MAX_CONSECUTIVE_SENSOR_ERRORS}) ---"
    )
    logger.warning(f"  Error type: {type(error).__name__}: {error}")
    logger.warning(f"  Service uptime: {uptime:.0f}s, time since last successful publish: {time_since_success:.0f}s")

    # Check power state — undervoltage is a common cause of I2C failures
    throttle = get_throttle_status()
    if throttle:
        if throttle["undervoltage_now"]:
            logger.warning(f"  Power: UNDERVOLTAGE NOW (throttled=0x{throttle['throttled']:x})")
        elif throttle["undervoltage"]:
            logger.warning(f"  Power: undervoltage since boot (throttled=0x{throttle['throttled']:x})")
        else:
            logger.warning(f"  Power: OK (throttled=0x{throttle['throttled']:x})")
    else:
        logger.warning("  Power: unable to read throttle status")

    # Scan I2C bus on first error and at recovery threshold to see what's responding
    if error_count == 1 or error_count == I2C_RECOVERY_THRESHOLD:
        logger.warning("  I2C bus scan:")
        for line in scan_i2c_devices().splitlines():
            logger.warning(f"    {line}")

    logger.warning("--- End diagnostics ---")


def get_throttle_status():
    """Read Pi throttle status from vcgencmd.

    Returns a dict with:
        throttled: raw hex value (int)
        undervoltage: True if undervoltage has occurred since boot
        undervoltage_now: True if undervoltage is happening right now
    """
    try:
        result = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5)
        # Output format: "throttled=0x50000"
        value = int(result.stdout.strip().split("=")[1], 16)
        status = {
            "throttled": value,
            "undervoltage": bool(value & (1 << 16)),
            "undervoltage_now": bool(value & (1 << 0)),
        }
        if status["undervoltage_now"]:
            logger.warning(f"Undervoltage detected NOW (throttled=0x{value:x})")
        elif status["undervoltage"]:
            logger.warning(f"Undervoltage has occurred since boot (throttled=0x{value:x})")
        return status
    except Exception as e:
        logger.debug(f"Failed to read throttle status: {e}")
        return None


def initialize_sensors():
    """Initialize weather sensor and CPU temperature monitor.

    Protected by SIGALRM timeout so a hung I2C bus during startup
    doesn't leave the process stuck forever (systemd Type=simple
    considers it running as soon as the process starts).
    """
    global sensor, cpu
    init_timeout = SENSOR_READ_TIMEOUT + 15  # extra margin for warmup sleep
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(init_timeout)
    try:
        logger.info("Initializing WeatherHAT sensor...")
        sensor = weatherhat.WeatherHAT()
        sensor.temperature_offset = TEMP_OFFSET

        logger.info("Initializing CPU temperature monitor...")
        cpu = CPUTemperature()

        # Warm up sensors - discard initial readings
        logger.info("Warming up sensors (10 seconds)...")
        sensor.update(interval=10.0)
        sleep(10.0)
        logger.info("Sensors initialized successfully")
        return True
    except SensorTimeout:
        logger.error(f"Sensor initialization timed out after {init_timeout}s (I2C bus may be hung)")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize sensors: {e}")
        return False
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def reinitialize_sensors():
    """Reinitialize sensors after I2C bus recovery.

    After bus recovery the driver is rebound and /dev/i2c-1 is recreated,
    so existing SMBus file descriptors are stale and must be reopened.
    """
    global sensor, cpu
    try:
        logger.info("Reinitializing sensors after I2C recovery...")
        sensor = weatherhat.WeatherHAT()
        sensor.temperature_offset = TEMP_OFFSET
        cpu = CPUTemperature()
        # Quick update to verify sensors are responsive (no warmup needed)
        sensor.update(interval=1.0)
        logger.info("Sensors reinitialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to reinitialize sensors after recovery: {e}")
        return False


def initialize_mqtt():
    """Initialize MQTT client with authentication and callbacks"""
    global mqtt_client
    try:
        logger.info(f"Initializing MQTT client (ID: {MQTT_CLIENT_ID})...")
        mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

        # Set up authentication if provided
        if MQTT_USERNAME and MQTT_PASSWORD:
            logger.info("Using MQTT authentication")
            mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # Set Last Will — broker publishes this if we disconnect unexpectedly
        mqtt_client.will_set(TOPICS['status'], payload="offline", qos=1, retain=True)

        # Register callbacks
        mqtt_client.on_connect = on_connect
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_message = on_message
        mqtt_client.on_publish = on_publish

        # Connect to broker
        logger.info(f"Connecting to MQTT broker at {MQTT_SERVER}:{MQTT_PORT}...")
        mqtt_client.connect(host=MQTT_SERVER, port=MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()

        return True
    except Exception as e:
        logger.error(f"Failed to initialize MQTT client: {e}")
        return False


def read_and_publish_data():
    """Read all sensor data and publish to MQTT"""
    global consecutive_sensor_errors, last_successful_publish
    try:
        # Set a timeout so a hung I2C bus doesn't block forever
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(SENSOR_READ_TIMEOUT)

        try:
            # Update sensor readings
            sensor.update(interval=UPDATE_INTERVAL)

            # Read all values
            wind_direction_cardinal = sensor.degrees_to_cardinal(sensor.wind_direction)

            sensor_data = {
                'cpu_temp': cpu.temperature,
                'temperature': sensor.temperature,
                'humidity': sensor.humidity,
                'relative_humidity': sensor.relative_humidity,
                'pressure': sensor.pressure,
                'dewpoint': sensor.dewpoint,
                'light': sensor.lux,
                'wind_direction': wind_direction_cardinal,
                'wind_speed': sensor.wind_speed,
                'rain': sensor.rain,
                'rain_total': sensor.rain_total,
            }
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Add throttle status (separate from I2C timeout — this calls vcgencmd)
        throttle = get_throttle_status()
        if throttle:
            sensor_data['throttled'] = throttle['throttled']
            sensor_data['undervoltage'] = throttle['undervoltage']
            sensor_data['undervoltage_now'] = throttle['undervoltage_now']

        # Publish all readings
        success_count = 0
        for key, value in sensor_data.items():
            if send_payload(mqtt_client, TOPICS[key], value):
                success_count += 1

        logger.debug(f"Published {success_count}/{len(sensor_data)} sensor readings")
        if consecutive_sensor_errors > 0:
            logger.info(f"Sensor reads recovered after {consecutive_sensor_errors} consecutive error(s)")
        consecutive_sensor_errors = 0
        last_successful_publish = monotonic()
        return True

    except (OSError, RuntimeError, SensorTimeout) as e:
        consecutive_sensor_errors += 1
        logger.error(f"I2C/Sensor error ({consecutive_sensor_errors}/{MAX_CONSECUTIVE_SENSOR_ERRORS}): {e}")
        log_sensor_diagnostics(e, consecutive_sensor_errors)

        # Attempt I2C bus recovery before giving up
        if consecutive_sensor_errors == I2C_RECOVERY_THRESHOLD:
            logger.warning(f"Hit {I2C_RECOVERY_THRESHOLD} consecutive errors, attempting I2C bus recovery...")
            if attempt_i2c_recovery():
                if reinitialize_sensors():
                    logger.info("I2C recovery and sensor reinitialization succeeded, resetting error counter")
                    consecutive_sensor_errors = 0
                    return False
                else:
                    logger.error("Sensors failed to reinitialize after bus recovery")

        if consecutive_sensor_errors >= MAX_CONSECUTIVE_SENSOR_ERRORS:
            time_since_success = monotonic() - last_successful_publish
            logger.critical(
                f"I2C bus failure: {consecutive_sensor_errors} consecutive errors over {time_since_success:.0f}s, "
                f"exiting for systemd restart (uptime: {monotonic() - service_start_time:.0f}s)"
            )
            os._exit(1)
        return False
    except Exception as e:
        logger.error(f"Error reading sensors: {e}", exc_info=True)
        return False


def main():
    """Main application loop"""
    global running, reconnect_delay

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting Weather Station MQTT Publisher")
    logger.info(f"Configuration: Server={MQTT_SERVER}, Port={MQTT_PORT}, Topic Prefix={MQTT_TOPIC_PREFIX}")

    # Initialize hardware
    if not initialize_sensors():
        logger.error("Sensor initialization failed. Exiting.")
        sys.exit(1)

    # Initialize MQTT
    if not initialize_mqtt():
        logger.error("MQTT initialization failed. Exiting.")
        sys.exit(1)

    logger.info("Starting main publish loop...")

    while running:
        if mqtt_client.is_connected():
            # Reset reconnect delay on successful operation
            reconnect_delay = INITIAL_RECONNECT_DELAY

            # Read and publish data
            read_and_publish_data()

            # Wait before next update
            sleep(PUBLISH_INTERVAL)

        else:
            # Connection lost - paho's network loop (loop_start) handles
            # reconnection automatically. Just wait and log.
            logger.warning(f"MQTT disconnected. Waiting {reconnect_delay}s for reconnection...")
            sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)

    # Cleanup
    logger.info("Shutting down...")
    if mqtt_client:
        mqtt_client.publish(TOPICS['status'], payload="offline", qos=1, retain=True)
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        main()
        os._exit(0)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        os._exit(1)
