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
        # Use unique_id from payloads instead of parsing topics, since both
        # client_id and sensor keys can contain underscores (e.g., weatherhat-pi_rain_total).
        # Match against known sensor keys by checking unique_id suffix.
        all_expected = EXPECTED_WEATHER_SENSORS | EXPECTED_PI_SENSORS
        found_keys = set()
        for payload in self.configs.values():
            uid = payload.get("unique_id", "")
            for key in all_expected:
                if uid.endswith(f"_{key}"):
                    found_keys.add(key)

        missing = all_expected - found_keys
        if missing:
            self.errors.append(f"Missing discovery configs for: {missing}")

        # Check both devices appeared using device name, not identifier suffix,
        # since the client_id itself may end with "-pi" (e.g., weatherhat-pi).
        device_names = set()
        for payload in self.configs.values():
            device = payload.get("device", {})
            name = device.get("name", "")
            if name:
                device_names.add(name)
        if "Weather Station" not in device_names:
            self.errors.append("No Weather Station device found")
        if "Weather Station Pi" not in device_names:
            self.errors.append("No Weather Station Pi device found")

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
        print("Waiting for discovery configs...")

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
