# HA MQTT Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish Home Assistant MQTT Discovery configs so HA auto-creates sensor entities for all weather and Pi system sensors.

**Architecture:** New `weatherhat/ha_discovery.py` module defines sensor metadata and generates discovery payloads. `bin/mqtt-publisher.py` calls it from `on_connect`. A test harness script validates the discovery flow against a live MQTT broker.

**Tech Stack:** Python 3.7+, paho-mqtt, JSON payloads conforming to HA MQTT Discovery schema.

**Spec:** `docs/superpowers/specs/2026-04-04-ha-mqtt-discovery-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `weatherhat/ha_discovery.py` | Sensor metadata, device definitions, discovery payload generation and publishing |
| Create | `tests/test_ha_discovery.py` | Unit tests for payload generation |
| Modify | `bin/mqtt-publisher.py:31-36` | Add `HA_DISCOVERY` env var |
| Modify | `bin/mqtt-publisher.py:106-120` | Call discovery from `on_connect` |
| Create | `scripts/test-ha-discovery.py` | Live MQTT test harness for validating discovery + data flow |
| Modify | `config/mqtt.env.example` | Add `HA_DISCOVERY` variable |
| Modify | `docs/MQTT.md` | Add discovery config and documentation section |
| Modify | `README.md` | Add autodiscovery to features list |

---

## Task 1: Create `weatherhat/ha_discovery.py` with sensor definitions and payload generation

**Files:**
- Create: `weatherhat/ha_discovery.py`
- Create: `tests/test_ha_discovery.py`

### Step 1: Write failing tests for discovery payload generation

- [ ] Create `tests/test_ha_discovery.py`:

```python
"""Tests for Home Assistant MQTT Discovery payload generation."""
import json
from unittest.mock import MagicMock, call

from weatherhat.ha_discovery import (
    PI_SENSORS,
    WEATHER_SENSORS,
    publish_discovery_configs,
)


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
```

- [ ] Run tests to verify they fail:

```bash
source .venv/bin/activate && python -m pytest tests/test_ha_discovery.py -v
```

Expected: `ModuleNotFoundError: No module named 'weatherhat.ha_discovery'`

### Step 2: Implement `weatherhat/ha_discovery.py`

- [ ] Create `weatherhat/ha_discovery.py`:

```python
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
```

### Step 3: Run tests and verify they pass

- [ ] Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_ha_discovery.py -v
```

Expected: All 10 tests pass.

### Step 4: Run linting

- [ ] Run:

```bash
source .venv/bin/activate && ruff check weatherhat/ha_discovery.py tests/test_ha_discovery.py && isort --check-only --diff weatherhat/ha_discovery.py tests/test_ha_discovery.py
```

Expected: No errors.

### Step 5: Commit

- [ ] Run:

```bash
git add weatherhat/ha_discovery.py tests/test_ha_discovery.py
git commit -m "Add HA MQTT Discovery module with sensor definitions and tests"
```

---

## Task 2: Integrate discovery into mqtt-publisher.py

**Files:**
- Modify: `bin/mqtt-publisher.py:31-36` (add env var)
- Modify: `bin/mqtt-publisher.py:106-120` (call from on_connect)

### Step 1: Add HA_DISCOVERY env var

- [ ] In `bin/mqtt-publisher.py`, after line 36 (`MQTT_TOPIC_PREFIX = ...`), add:

```python
# Home Assistant MQTT Discovery (default: enabled, set HA_DISCOVERY=false to disable)
HA_DISCOVERY = os.getenv("HA_DISCOVERY", "true").lower() != "false"
```

### Step 2: Add import

- [ ] In `bin/mqtt-publisher.py`, after line 21 (`from weatherhat.i2c_recovery import attempt_i2c_recovery`), add:

```python
from weatherhat.ha_discovery import publish_discovery_configs
```

### Step 3: Call discovery from on_connect

- [ ] In `bin/mqtt-publisher.py`, in the `on_connect` function, after the `client.publish(TOPICS['status'], ...)` line (line 111), add:

```python
        if HA_DISCOVERY:
            publish_discovery_configs(client, MQTT_TOPIC_PREFIX, MQTT_CLIENT_ID)
```

### Step 4: Run linting

- [ ] Run:

```bash
source .venv/bin/activate && ruff check bin/mqtt-publisher.py && isort --check-only --diff bin/mqtt-publisher.py
```

Expected: No errors.

### Step 5: Commit

- [ ] Run:

```bash
git add bin/mqtt-publisher.py
git commit -m "Integrate HA MQTT Discovery into publisher on_connect"
```

---

## Task 3: Create live test harness

**Files:**
- Create: `scripts/test-ha-discovery.py`

### Step 1: Write the test harness

- [ ] Create `scripts/test-ha-discovery.py`:

```python
#!/usr/bin/env python3
"""Test harness for Home Assistant MQTT Discovery.

Connects to an MQTT broker, subscribes to discovery topics,
validates payloads, then subscribes to state topics and
verifies sensor data arrives. Does not require Home Assistant.

Usage:
    python3 scripts/test-ha-discovery.py --host mqtt.example.com
    python3 scripts/test-ha-discovery.py --host mqtt.example.com --timeout 30
"""
import argparse
import json
import re
import sys
import threading
from collections import defaultdict

import paho.mqtt.client as mqtt

REQUIRED_KEYS = {"name", "state_topic", "unique_id", "device", "value_template"}
EXPECTED_WEATHER_SENSORS = {"temperature", "humidity", "relative_humidity", "pressure", "dewpoint", "light", "wind_speed", "wind_direction", "rain", "rain_total"}
EXPECTED_PI_SENSORS = {"cpu_temp", "throttled", "undervoltage", "undervoltage_now"}


class DiscoveryValidator:
    def __init__(self):
        self.configs = {}  # topic -> parsed payload
        self.data_received = defaultdict(list)  # state_topic -> [payloads]
        self.errors = []
        self.state_topics = set()
        self.device_ids = set()
        self.discovery_done = threading.Event()
        self.data_done = threading.Event()

    def on_discovery(self, topic, payload_str):
        """Validate a discovery config message."""
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {topic}: {e}")
            return

        self.configs[topic] = payload

        # Check required keys
        missing = REQUIRED_KEYS - set(payload.keys())
        if missing:
            self.errors.append(f"{topic}: missing keys {missing}")

        # Check device object
        device = payload.get("device", {})
        if "identifiers" not in device:
            self.errors.append(f"{topic}: device missing identifiers")
        else:
            for ident in device["identifiers"]:
                self.device_ids.add(ident)

        # Check availability
        if "availability_topic" not in payload:
            self.errors.append(f"{topic}: missing availability_topic")

        # Track state topic for phase 2
        if "state_topic" in payload:
            self.state_topics.add(payload["state_topic"])

    def on_data(self, topic, payload_str):
        """Validate a sensor data message."""
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON on {topic}: {e}")
            return

        # Check that the key referenced by value_template exists
        if topic not in payload:
            self.errors.append(f"Data payload on {topic} missing expected key '{topic}' (got keys: {list(payload.keys())})")

        self.data_received[topic].append(payload)

    def check_completeness(self):
        """Check that all expected sensors were discovered."""
        found_keys = set()
        for topic in self.configs:
            # Extract sensor key from homeassistant/sensor/{client_id}_{key}/config
            match = re.search(r'/sensor/[^/]+_([^/]+)/config$', topic)
            if match:
                found_keys.add(match.group(1))

        all_expected = EXPECTED_WEATHER_SENSORS | EXPECTED_PI_SENSORS
        missing = all_expected - found_keys
        if missing:
            self.errors.append(f"Missing discovery configs for: {missing}")

        # Check both devices appeared
        has_weather = any(not ident.endswith("-pi") for ident in self.device_ids)
        has_pi = any(ident.endswith("-pi") for ident in self.device_ids)
        if not has_weather:
            self.errors.append("No Weather Station device found")
        if not has_pi:
            self.errors.append("No Pi System device found")

    def report(self):
        """Print results and return exit code."""
        print(f"\n{'='*50}")
        print("HA MQTT Discovery Test Results")
        print(f"{'='*50}")
        print(f"Discovery configs received: {len(self.configs)}")
        print(f"Devices found: {self.device_ids}")
        print(f"State topics with data: {len(self.data_received)}/{len(self.state_topics)}")

        if self.data_received:
            print("\nData received:")
            for topic in sorted(self.data_received):
                print(f"  {topic}: {len(self.data_received[topic])} message(s)")

        no_data = self.state_topics - set(self.data_received.keys())
        if no_data:
            print(f"\nNo data received for: {sorted(no_data)}")

        if self.errors:
            print(f"\nErrors ({len(self.errors)}):")
            for err in self.errors:
                print(f"  - {err}")
            return 1

        print("\nAll checks passed!")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Validate HA MQTT Discovery")
    parser.add_argument("--host", required=True, help="MQTT broker hostname")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", default=None, help="MQTT username")
    parser.add_argument("--password", default=None, help="MQTT password")
    parser.add_argument("--timeout", type=int, default=15, help="Seconds to wait for data after discovery")
    args = parser.parse_args()

    validator = DiscoveryValidator()
    discovery_timer = None

    def on_connect(client, userdata, flags, rc):
        nonlocal discovery_timer
        if rc != 0:
            print(f"Connection failed: rc={rc}")
            sys.exit(1)
        print(f"Connected to {args.host}:{args.port}")
        client.subscribe("homeassistant/sensor/+/config", qos=1)
        print("Subscribed to homeassistant/sensor/+/config")
        print(f"Waiting for discovery configs...")

        # Give discovery configs time to arrive (they're retained)
        def discovery_timeout():
            validator.discovery_done.set()
        discovery_timer = threading.Timer(3.0, discovery_timeout)
        discovery_timer.start()

    def on_message(client, userdata, msg):
        nonlocal discovery_timer
        topic = msg.topic
        payload_str = msg.payload.decode()

        if topic.startswith("homeassistant/sensor/") and topic.endswith("/config"):
            validator.on_discovery(topic, payload_str)
            # Reset discovery timer on each new config
            if discovery_timer:
                discovery_timer.cancel()
            discovery_timer = threading.Timer(2.0, lambda: validator.discovery_done.set())
            discovery_timer.start()
        else:
            validator.on_data(topic, payload_str)

    client = mqtt.Client(client_id="ha-discovery-test")
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_start()

        # Phase 1: Wait for discovery configs
        validator.discovery_done.wait(timeout=10)

        if not validator.configs:
            print("No discovery configs received. Is the weather station running with HA_DISCOVERY enabled?")
            sys.exit(1)

        validator.check_completeness()
        print(f"Received {len(validator.configs)} discovery configs")

        # Phase 2: Subscribe to state topics and wait for data
        for state_topic in validator.state_topics:
            client.subscribe(state_topic, qos=1)
        print(f"Subscribed to {len(validator.state_topics)} state topics, waiting {args.timeout}s for data...")

        validator.data_done.wait(timeout=args.timeout)

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        client.loop_stop()
        client.disconnect()

    sys.exit(validator.report())


if __name__ == "__main__":
    main()
```

### Step 2: Run linting

- [ ] Run:

```bash
source .venv/bin/activate && ruff check scripts/test-ha-discovery.py && isort --check-only --diff scripts/test-ha-discovery.py
```

Expected: No errors.

### Step 3: Commit

- [ ] Run:

```bash
git add scripts/test-ha-discovery.py
git commit -m "Add live test harness for HA MQTT Discovery validation"
```

---

## Task 4: Update configuration and documentation

**Files:**
- Modify: `config/mqtt.env.example`
- Modify: `docs/MQTT.md`
- Modify: `README.md`

### Step 1: Add HA_DISCOVERY to mqtt.env.example

- [ ] Append to `config/mqtt.env.example` after `PUBLISH_INTERVAL=5.0`:

```bash

# Home Assistant MQTT Discovery (default: true, set to false to disable)
HA_DISCOVERY=true
```

### Step 2: Update docs/MQTT.md configuration table

- [ ] Add row to the configuration table in `docs/MQTT.md` (after the `PUBLISH_INTERVAL` row):

```
| `HA_DISCOVERY` | `true` | Enable Home Assistant MQTT Discovery |
```

### Step 3: Add discovery section to docs/MQTT.md

- [ ] Add a new section in `docs/MQTT.md` after the "Integration Examples" section (before "Troubleshooting"):

```markdown
## Home Assistant Discovery

When `HA_DISCOVERY` is enabled (the default), the publisher sends [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) config messages on every connect. Home Assistant automatically creates sensor entities — no manual `configuration.yaml` needed.

### Discovered Entities

Two devices are created in Home Assistant:

**Weather Station** (Pimoroni Weather HAT):
- Temperature, Humidity, Relative Humidity, Pressure, Dew Point
- Light, Wind Speed, Wind Direction
- Rain Rate, Rain Total

**Weather Station Pi** (Raspberry Pi):
- CPU Temperature, Throttle Status
- Undervoltage, Undervoltage Now

All entities include availability tracking via the `sensors/weather/status` LWT topic.

### Disabling Discovery

Set `HA_DISCOVERY=false` in `config/mqtt.env` and restart the service. Existing entities in HA will become unavailable but won't be automatically removed.

### Validating Discovery

Use the test harness to verify discovery payloads without a Home Assistant installation:

```bash
python3 scripts/test-ha-discovery.py --host YOUR_MQTT_SERVER --timeout 30
```
```

### Step 4: Update README.md features list

- [ ] In `README.md`, add after the "System Monitoring" feature line:

```markdown
- **Home Assistant Discovery** - Automatic entity creation via MQTT Discovery (opt-out with `HA_DISCOVERY=false`)
```

### Step 5: Run linting

- [ ] Run:

```bash
source .venv/bin/activate && ruff check . && isort --check-only --diff . && codespell --skip='.git,*.pyc,__pycache__,dist,build,.tox,.egg'
```

Expected: All checks pass.

### Step 6: Commit

- [ ] Run:

```bash
git add config/mqtt.env.example docs/MQTT.md README.md
git commit -m "Document HA MQTT Discovery config and update README features"
```

---

## Task 5: Final validation and PR

### Step 1: Run full test suite

- [ ] Run:

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests pass.

### Step 2: Run full linting

- [ ] Run:

```bash
source .venv/bin/activate && ruff check . && isort --check-only --diff . && codespell --skip='.git,*.pyc,__pycache__,dist,build,.tox,.egg'
```

Expected: All checks pass.

### Step 3: Deploy to Pi and run test harness

Manual step — deploy via `update.sh`, then:

```bash
python3 scripts/test-ha-discovery.py --host YOUR_MQTT_SERVER --timeout 30
```

Expected: All 14 entities discovered, data received, all checks pass.

### Step 4: Push branch and create PR

- [ ] Run:

```bash
git push github ha-mqtt-discovery
```

Then create PR against `main` referencing issue #1.
