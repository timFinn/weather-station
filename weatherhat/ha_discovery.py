"""Home Assistant MQTT Discovery for Weather Station sensors.

Publishes discovery config payloads so Home Assistant automatically
creates sensor entities. Called on every MQTT connect to handle
HA/broker restarts.

Reference: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
"""
import json
import logging

logger = logging.getLogger(__name__)

# Weather sensors — grouped under the Weather Station device.
# Keys must match the TOPICS keys in mqtt-publisher.py.
# "subtopic" maps the key to its MQTT topic segment (weather/ or pi/).
WEATHER_SENSORS = {
    "temperature": {
        "name": "Temperature",
        "device_class": "temperature",
        "unit_of_measurement": "\u00b0C",
        "state_class": "measurement",
        "subtopic": "weather/temperature",
    },
    "humidity": {
        "name": "Humidity",
        "device_class": "humidity",
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "subtopic": "weather/humidity",
    },
    "relative_humidity": {
        "name": "Relative Humidity",
        "device_class": "humidity",
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "subtopic": "weather/relative_humidity",
    },
    "pressure": {
        "name": "Pressure",
        "device_class": "atmospheric_pressure",
        "unit_of_measurement": "hPa",
        "state_class": "measurement",
        "subtopic": "weather/pressure",
    },
    "dewpoint": {
        "name": "Dew Point",
        "device_class": "temperature",
        "unit_of_measurement": "\u00b0C",
        "state_class": "measurement",
        "subtopic": "weather/dewpoint",
    },
    "light": {
        "name": "Light",
        "device_class": "illuminance",
        "unit_of_measurement": "lx",
        "state_class": "measurement",
        "subtopic": "weather/light",
    },
    "wind_speed": {
        "name": "Wind Speed",
        "device_class": "wind_speed",
        "unit_of_measurement": "m/s",
        "state_class": "measurement",
        "subtopic": "weather/wind_speed",
    },
    "wind_direction": {
        "name": "Wind Direction",
        "icon": "mdi:windsock",
        "subtopic": "weather/wind_direction",
    },
    "rain": {
        "name": "Rain Rate",
        "device_class": "precipitation_intensity",
        "unit_of_measurement": "mm/s",
        "state_class": "measurement",
        "subtopic": "weather/rain",
    },
    "rain_total": {
        "name": "Rain Total",
        "device_class": "precipitation",
        "unit_of_measurement": "mm",
        "state_class": "total_increasing",
        "subtopic": "weather/rain_total",
    },
}

# Pi system sensors — grouped under the Pi System device.
PI_SENSORS = {
    "cpu_temp": {
        "name": "CPU Temperature",
        "device_class": "temperature",
        "unit_of_measurement": "\u00b0C",
        "state_class": "measurement",
        "subtopic": "pi/cpu_temp",
    },
    "throttled": {
        "name": "Throttle Status",
        "icon": "mdi:gauge",
        "subtopic": "pi/throttled",
    },
    "undervoltage": {
        "name": "Undervoltage",
        "icon": "mdi:flash-alert",
        "subtopic": "pi/undervoltage",
    },
    "undervoltage_now": {
        "name": "Undervoltage Now",
        "icon": "mdi:flash-alert-outline",
        "subtopic": "pi/undervoltage_now",
    },
}


def _build_device(client_id, variant):
    """Build an HA device object.

    Args:
        client_id: MQTT client ID used as device identifier.
        variant: "weather" or "pi".
    """
    if variant == "weather":
        return {
            "identifiers": [client_id],
            "name": "Weather Station",
            "model": "Weather HAT",
            "manufacturer": "Pimoroni",
        }
    return {
        "identifiers": [f"{client_id}-pi"],
        "name": "Weather Station Pi",
        "model": "Raspberry Pi",
        "manufacturer": "Raspberry Pi",
    }


def _build_config_payload(sensor_key, sensor_def, topic_prefix, client_id, device):
    """Build a single HA discovery config payload.

    Args:
        sensor_key: Key name (e.g., "temperature").
        sensor_def: Dict with name, device_class, unit, etc.
        topic_prefix: MQTT topic prefix (e.g., "sensors").
        client_id: MQTT client ID for unique_id generation.
        device: HA device object dict.

    Returns:
        dict: Discovery config payload.
    """
    state_topic = f"{topic_prefix}/{sensor_def['subtopic']}"
    payload = {
        "name": sensor_def["name"],
        "state_topic": state_topic,
        "value_template": "{{ " + f"value_json['{state_topic}']" + " }}",
        "unique_id": f"{client_id}_{sensor_key}",
        "device": device,
        "availability_topic": f"{topic_prefix}/weather/status",
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    # Add optional fields only when present
    for field in ("device_class", "unit_of_measurement", "state_class", "icon"):
        if field in sensor_def:
            payload[field] = sensor_def[field]

    return payload


def publish_discovery_configs(client, topic_prefix, client_id):
    """Publish HA MQTT Discovery config for all sensors.

    Sends a retained config message per sensor to
    homeassistant/sensor/{client_id}_{key}/config.
    Called on every MQTT connect so HA picks up configs
    after broker or HA restarts.

    Args:
        client: Connected paho MQTT client instance.
        topic_prefix: MQTT topic prefix (e.g., "sensors").
        client_id: MQTT client ID, used for unique_id and device identifier.
    """
    weather_device = _build_device(client_id, "weather")
    pi_device = _build_device(client_id, "pi")

    published = 0
    for sensors, device in [(WEATHER_SENSORS, weather_device), (PI_SENSORS, pi_device)]:
        for key, sensor_def in sensors.items():
            config = _build_config_payload(key, sensor_def, topic_prefix, client_id, device)
            topic = f"homeassistant/sensor/{client_id}_{key}/config"
            result = client.publish(topic=topic, payload=json.dumps(config), qos=1, retain=True)
            if result.rc == 0:
                published += 1
            else:
                logger.warning(f"Failed to publish discovery config for {key}: rc={result.rc}")

    logger.info(f"Published {published} HA discovery configs")
