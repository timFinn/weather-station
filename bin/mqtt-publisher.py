#!/usr/bin/env python3
"""
MQTT Weather Station Publisher

Reads data from WeatherHAT and publishes to MQTT broker.
Configure via environment variables or config file.
"""
import os
import sys
import json
import logging
import signal
from time import sleep

import weatherhat
from gpiozero import CPUTemperature
import paho.mqtt.client as mqtt

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
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "weatherhat")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")

# Sensor configuration
TEMP_OFFSET = float(os.getenv("TEMP_OFFSET", "-7.5"))
UPDATE_INTERVAL = float(os.getenv("UPDATE_INTERVAL", "2.0"))
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "2.0"))

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
}

# Global state
sensor = None
cpu = None
mqtt_client = None
running = True
reconnect_delay = INITIAL_RECONNECT_DELAY


#  Function Definitions

def signal_handler(sig, frame):
    """Handle graceful shutdown on SIGINT/SIGTERM"""
    global running
    logger.info("Shutdown signal received, cleaning up...")
    running = False


def on_connect(client, userdata, flags, rc):
    """Callback when MQTT connection is established"""
    global reconnect_delay
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_SERVER}:{MQTT_PORT}")
        reconnect_delay = INITIAL_RECONNECT_DELAY  # Reset backoff on successful connect
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
        result = client.publish(topic=topic, payload=payload, qos=1, retain=False)

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

def initialize_sensors():
    """Initialize weather sensor and CPU temperature monitor"""
    global sensor, cpu
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
    except Exception as e:
        logger.error(f"Failed to initialize sensors: {e}")
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

        # Publish all readings
        success_count = 0
        for key, value in sensor_data.items():
            if send_payload(mqtt_client, TOPICS[key], value):
                success_count += 1

        logger.debug(f"Published {success_count}/{len(sensor_data)} sensor readings")
        return True

    except OSError as e:
        logger.error(f"I2C/Sensor error: {e}")
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
            # Connection lost - attempt reconnect with exponential backoff
            logger.warning(f"MQTT disconnected. Retrying in {reconnect_delay}s...")

            try:
                mqtt_client.reconnect()
                logger.info("Reconnection successful")
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")

                # Exponential backoff with max limit
                sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)

    # Cleanup
    logger.info("Shutting down...")
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

