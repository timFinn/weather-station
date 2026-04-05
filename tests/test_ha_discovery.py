"""Tests for Home Assistant MQTT Discovery payload generation."""
import json
import sys
from unittest.mock import MagicMock

# Mock hardware dependencies so ha_discovery can be imported without Pi hardware
for mod in ["gpiod", "gpiod.line", "gpiodevice", "ioexpander", "bme280", "ltr559", "smbus2", "st7789"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from weatherhat.ha_discovery import PI_SENSORS, WEATHER_SENSORS, publish_discovery_configs  # noqa: E402


def test_weather_sensor_keys_match_expected():
    """All expected weather sensor keys are defined."""
    expected = {"temperature", "humidity", "relative_humidity", "pressure", "dewpoint", "light", "wind_speed", "wind_direction", "rain", "rain_total"}
    assert set(WEATHER_SENSORS.keys()) == expected


def test_pi_sensor_keys_match_expected():
    """All expected Pi sensor keys are defined."""
    expected = {"cpu_temp", "throttled", "undervoltage", "undervoltage_now"}
    assert set(PI_SENSORS.keys()) == expected


def test_publish_sends_config_for_every_sensor():
    """One retained config message is published per sensor."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    total_sensors = len(WEATHER_SENSORS) + len(PI_SENSORS)
    assert client.publish.call_count == total_sensors


def test_weather_sensor_discovery_payload_structure():
    """Weather sensor payloads contain all required HA fields."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    # Find the temperature config call
    for c in client.publish.call_args_list:
        topic = c.kwargs["topic"]
        if "temperature" in topic and "cpu" not in topic:
            payload = json.loads(c.kwargs["payload"])
            assert payload["name"] == "Temperature"
            assert payload["device_class"] == "temperature"
            assert payload["unit_of_measurement"] == "\u00b0C"
            assert payload["state_class"] == "measurement"
            assert payload["state_topic"] == "sensors/weather/temperature"
            assert "sensors/weather/temperature" in payload["value_template"]
            assert payload["unique_id"] == "weatherhat-test_temperature"
            assert payload["availability_topic"] == "sensors/weather/status"
            assert payload["payload_available"] == "online"
            assert payload["payload_not_available"] == "offline"
            # Device object
            assert payload["device"]["identifiers"] == ["weatherhat-test"]
            assert payload["device"]["name"] == "Weather Station"
            assert payload["device"]["model"] == "Weather HAT"
            assert payload["device"]["manufacturer"] == "Pimoroni"
            return
    raise AssertionError("No temperature discovery config found")


def test_pi_sensor_discovery_payload_structure():
    """Pi sensor payloads use the Pi device object."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    for c in client.publish.call_args_list:
        topic = c.kwargs["topic"]
        if "cpu_temp" in topic:
            payload = json.loads(c.kwargs["payload"])
            assert payload["state_topic"] == "sensors/pi/cpu_temp"
            assert payload["device"]["identifiers"] == ["weatherhat-test-pi"]
            assert payload["device"]["name"] == "Weather Station Pi"
            return
    raise AssertionError("No cpu_temp discovery config found")


def test_discovery_topic_format():
    """Discovery topics follow homeassistant/sensor/{id}/config pattern."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    for c in client.publish.call_args_list:
        topic = c.kwargs["topic"]
        assert topic.startswith("homeassistant/sensor/"), f"Bad topic: {topic}"
        assert topic.endswith("/config"), f"Bad topic: {topic}"


def test_discovery_publishes_retained_qos1():
    """All discovery messages use retain=True and qos=1."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    for c in client.publish.call_args_list:
        assert c.kwargs["retain"] is True, f"Not retained: {c}"
        assert c.kwargs["qos"] == 1, f"Not QoS 1: {c}"


def test_sensors_without_device_class_have_icon():
    """wind_direction, throttled, undervoltage sensors have icons instead of device_class."""
    icon_sensors = {"wind_direction", "throttled", "undervoltage", "undervoltage_now"}
    all_sensors = {**WEATHER_SENSORS, **PI_SENSORS}
    for key in icon_sensors:
        sensor = all_sensors[key]
        assert "device_class" not in sensor, f"{key} should not have device_class"
        assert "icon" in sensor, f"{key} should have icon"


def test_custom_topic_prefix():
    """Discovery payloads use the provided topic prefix."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "myprefix", "weatherhat-test")

    for c in client.publish.call_args_list:
        payload = json.loads(c.kwargs["payload"])
        assert payload["state_topic"].startswith("myprefix/")
        assert payload["availability_topic"] == "myprefix/weather/status"


def test_unique_ids_are_all_unique():
    """Every sensor gets a distinct unique_id."""
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)

    publish_discovery_configs(client, "sensors", "weatherhat-test")

    unique_ids = set()
    for c in client.publish.call_args_list:
        payload = json.loads(c.kwargs["payload"])
        uid = payload["unique_id"]
        assert uid not in unique_ids, f"Duplicate unique_id: {uid}"
        unique_ids.add(uid)
