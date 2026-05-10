#!/usr/bin/env python3
"""
Weather HAT Display - MQTT Subscriber Edition

Renders the weather HAT LCD from MQTT topics published by the
weatherhat.service publisher. The display does not touch the sensor
hardware directly: under libgpiod v2, GPIO line ownership is exclusive
per-process, so two services both calling WeatherHAT() would fight over
the IO Expander interrupt line. This process only owns its own LCD and
the four navigation buttons.
"""
import json
import logging
import os
import platform
import select
import threading
import time
from dataclasses import dataclass
from datetime import timedelta

import gpiod
import gpiodevice
import paho.mqtt.client as mqtt
import st7789
from fonts.ttf import ManropeBold as UserFont
from gpiod.line import Bias, Edge
from PIL import Image, ImageDraw, ImageFont

from weatherhat import history

# Timing
SLEEP_TIMEOUT = int(os.getenv("DISPLAY_SLEEP_TIMEOUT", "30"))  # seconds
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "5.0"))
STALE_AFTER = 2 * PUBLISH_INTERVAL  # treat data as stale past this

# MQTT (mirrors mqtt-publisher.py so both read the same env file)
MQTT_SERVER = os.getenv("MQTT_SERVER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID_DISPLAY", f"weatherhat-display-{platform.node()}")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")

# Display
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240
SPI_SPEED_MHZ = 80
FPS = 5

# Buttons
BUTTONS = [5, 6, 16, 24]
BUTTON_LABELS = {5: 'A', 6: 'B', 16: 'X', 24: 'Y'}

# Colors
COLOR_WHITE = (255, 255, 255)
COLOR_BLUE = (31, 137, 251)
COLOR_GREEN = (99, 255, 124)
COLOR_YELLOW = (254, 219, 82)
COLOR_RED = (247, 0, 63)
COLOR_BLACK = (0, 0, 0)
COLOR_GREY = (100, 100, 100)
COLOR_CYAN = (0, 255, 255)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SensorState:
    """Latest scalar reading per sensor, populated from MQTT messages."""
    temperature: float = 0.0
    humidity: float = 0.0
    pressure: float = 0.0
    wind_speed: float = 0.0
    wind_direction: str = "?"  # Cardinal string (publisher-formatted)
    rain: float = 0.0
    lux: float = 0.0


class DisplayManager:
    """Manages display state, sleep/wake, and rendering."""

    def __init__(self):
        self.display = st7789.ST7789(
            rotation=90,
            port=0,
            cs=1,
            dc=9,
            backlight=12,
            spi_speed_hz=SPI_SPEED_MHZ * 1000 * 1000
        )
        self.display.begin()

        # 2x canvas for anti-aliased downscale
        self.image = Image.new("RGB", (DISPLAY_WIDTH * 2, DISPLAY_HEIGHT * 2), color=COLOR_BLACK)
        self.draw = ImageDraw.Draw(self.image)

        self.font_huge = ImageFont.truetype(UserFont, 100)
        self.font_large = ImageFont.truetype(UserFont, 60)
        self.font_medium = ImageFont.truetype(UserFont, 40)
        self.font_small = ImageFont.truetype(UserFont, 28)

        self.awake = False
        self.current_view = 'overview'
        self.last_activity = 0

    def wake(self):
        if not self.awake:
            self.display.set_backlight(0xFFFF)
            self.awake = True
        self.last_activity = time.time()

    def sleep(self):
        if self.awake:
            self.display.set_backlight(0)
            self.awake = False

    def check_sleep(self):
        if self.awake and (time.time() - self.last_activity) > SLEEP_TIMEOUT:
            self.sleep()

    def clear(self):
        self.draw.rectangle((0, 0, DISPLAY_WIDTH * 2, DISPLAY_HEIGHT * 2), COLOR_BLACK)

    def render(self):
        if self.awake:
            scaled = self.image.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.LANCZOS)
            self.display.display(scaled)


class MqttSensorSubscriber:
    """Subscribes to the weather publisher's MQTT topics and keeps the
    latest SensorState plus rolling history buffers for graphs.

    Thread-safe: paho's on_message fires on its own network-loop thread,
    so all state mutation happens under _lock.
    """

    # Topic suffix → (SensorState attr, history attr or None)
    _TOPIC_MAP = {
        "temperature": ("temperature", "temp_history"),
        "humidity": ("humidity", "humidity_history"),
        "pressure": ("pressure", "pressure_history"),
        "wind_speed": ("wind_speed", "wind_speed_history"),
        "wind_direction": ("wind_direction", None),  # cardinal string, no graph
        "rain": ("rain", "rain_history"),
        "light": ("lux", "light_history"),
    }

    def __init__(self):
        self.sensor = SensorState()
        self._lock = threading.Lock()
        self._last_message_time = 0.0
        self._publisher_status = "unknown"
        self._has_data = False

        # 10 minutes at 2-second intervals = 300 points
        self.temp_history = history.History(history_depth=300)
        self.pressure_history = history.History(history_depth=300)
        self.humidity_history = history.History(history_depth=300)
        self.wind_speed_history = history.WindSpeedHistory(history_depth=300)
        self.rain_history = history.History(history_depth=300)
        self.light_history = history.History(history_depth=300)

        self._weather_prefix = f"{MQTT_TOPIC_PREFIX}/weather/"
        self._status_topic = f"{self._weather_prefix}status"

        self._client = mqtt.Client(client_id=MQTT_CLIENT_ID)
        if MQTT_USERNAME and MQTT_PASSWORD:
            self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def connect(self):
        logger.info(f"Connecting to MQTT broker at {MQTT_SERVER}:{MQTT_PORT} as {MQTT_CLIENT_ID}")
        self._client.connect(host=MQTT_SERVER, port=MQTT_PORT, keepalive=60)
        self._client.loop_start()

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()

    @property
    def has_data(self):
        with self._lock:
            return self._has_data

    @property
    def publisher_online(self):
        with self._lock:
            return self._publisher_status == "online"

    @property
    def is_stale(self):
        with self._lock:
            if self._last_message_time == 0:
                return True
            return (time.time() - self._last_message_time) > STALE_AFTER

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker; subscribing to weather topics")
            client.subscribe(f"{self._weather_prefix}#", qos=1)
        else:
            logger.error(f"MQTT connection failed with rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(f"Unexpected disconnect from MQTT (rc={rc})")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        if not topic.startswith(self._weather_prefix):
            return

        # Status is published as a bare string ("online"/"offline"), not
        # JSON-wrapped like the scalar topics — handle it before json.loads.
        if topic == self._status_topic:
            status = msg.payload.decode(errors="replace").strip()
            with self._lock:
                self._publisher_status = status or "unknown"
            logger.info(f"Publisher status: {self._publisher_status}")
            return

        suffix = topic[len(self._weather_prefix):]
        mapping = self._TOPIC_MAP.get(suffix)
        if mapping is None:
            return

        try:
            payload = json.loads(msg.payload.decode())
            # Publisher wraps values as {topic: value} for Telegraf compat
            value = payload.get(topic) if isinstance(payload, dict) else payload
        except (ValueError, UnicodeDecodeError) as e:
            logger.debug(f"Could not parse {topic}: {e}")
            return

        attr, history_attr = mapping
        with self._lock:
            setattr(self.sensor, attr, value)
            if history_attr is not None and isinstance(value, (int, float)):
                getattr(self, history_attr).append(float(value))
            self._last_message_time = time.time()
            self._has_data = True


class ViewRenderer:
    """Renders views onto the DisplayManager's canvas."""

    def __init__(self, display_mgr):
        self.disp = display_mgr

    def _draw_offline_banner(self, reason):
        """Draw a red strip across the top indicating the publisher is offline or stale."""
        d = self.disp.draw
        d.rectangle((0, 0, DISPLAY_WIDTH * 2, 40), fill=COLOR_RED)
        d.text((240, 20), reason, font=self.disp.font_small, fill=COLOR_WHITE, anchor="mm")

    def _status_banner(self, data):
        """Return banner text if data is stale/offline, else None."""
        if not data.publisher_online:
            return "PUBLISHER OFFLINE"
        if data.is_stale:
            return "DATA STALE"
        return None

    def draw_waiting(self, reason):
        """Draw the pre-data placeholder screen."""
        self.disp.clear()
        d = self.disp.draw
        d.text((240, 200), "WEATHER", font=self.disp.font_large, fill=COLOR_CYAN, anchor="mm")
        d.text((240, 280), reason, font=self.disp.font_medium, fill=COLOR_GREY, anchor="mm")

    def draw_overview(self, data):
        self.disp.clear()
        d = self.disp.draw

        banner = self._status_banner(data)
        title_y = 60 if banner else 30
        if banner:
            self._draw_offline_banner(banner)

        d.text((240, title_y), "WEATHER", font=self.disp.font_large, fill=COLOR_CYAN, anchor="mm")

        temp_str = f"{data.sensor.temperature:.1f}°C"
        d.text((240, 140), temp_str, font=self.disp.font_huge, fill=COLOR_YELLOW, anchor="mm")

        readings = [
            (f"{data.sensor.humidity:.0f}%", "Humidity", COLOR_BLUE),
            (f"{data.sensor.pressure:.0f}", "hPa", COLOR_GREEN),
            (f"{data.sensor.wind_speed:.1f}", "m/s", COLOR_WHITE),
            (data.sensor.wind_direction, "Wind", COLOR_WHITE),
            (f"{data.sensor.rain:.1f}", "mm/s", COLOR_BLUE),
            (f"{data.sensor.lux:.0f}", "lux", COLOR_YELLOW),
        ]

        y_start = 260
        x_positions = [80, 240, 400]
        for i, (value, label, color) in enumerate(readings):
            row = i // 3
            col = i % 3
            x = x_positions[col]
            y = y_start + (row * 90)
            d.text((x, y), value, font=self.disp.font_medium, fill=color, anchor="mm")
            d.text((x, y + 35), label, font=self.disp.font_small, fill=COLOR_GREY, anchor="mm")

        d.text((240, 460), "B:Temp X:Wind Y:Rain", font=self.disp.font_small, fill=COLOR_GREY, anchor="mm")

    def draw_graph(self, data, title, history_data, unit, color, min_val=None, max_val=None):
        self.disp.clear()
        d = self.disp.draw

        banner = self._status_banner(data)
        title_y = 60 if banner else 30
        if banner:
            self._draw_offline_banner(banner)

        d.text((240, title_y), title, font=self.disp.font_large, fill=color, anchor="mm")

        if len(history_data._history) > 0:
            current = history_data.latest().value
            current_str = f"{current:.1f}{unit}"
            d.text((240, 130), current_str, font=self.disp.font_huge, fill=COLOR_WHITE, anchor="mm")

        graph_x = 40
        graph_y = 200
        graph_w = 400
        graph_h = 220

        points = history_data.history()
        if len(points) < 2:
            d.text((240, 310), "Collecting data...", font=self.disp.font_medium,
                   fill=COLOR_GREY, anchor="mm")
            return

        values = [p.value for p in points]

        if min_val is None:
            min_val = min(values) * 0.95
        if max_val is None:
            max_val = max(values) * 1.05

        if max_val == min_val:
            max_val = min_val + 1

        d.rectangle((graph_x, graph_y, graph_x + graph_w, graph_y + graph_h), outline=COLOR_GREY)
        d.text((graph_x - 10, graph_y), f"{max_val:.0f}", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="rm")
        d.text((graph_x - 10, graph_y + graph_h), f"{min_val:.0f}", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="rm")

        num_points = len(values)
        x_step = graph_w / max(1, num_points - 1)
        for i in range(num_points - 1):
            y1 = graph_y + graph_h - ((values[i] - min_val) / (max_val - min_val) * graph_h)
            y2 = graph_y + graph_h - ((values[i + 1] - min_val) / (max_val - min_val) * graph_h)
            x1 = graph_x + (i * x_step)
            x2 = graph_x + ((i + 1) * x_step)
            d.line((x1, y1, x2, y2), fill=color, width=3)

        timespan = f"Last {len(points) * 2}s"
        d.text((240, 460), f"{timespan} • A:Overview", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="mm")


def main():
    logger.info("Weather HAT Display - MQTT Subscriber Edition")
    logger.info("Press any button to wake. A: Overview | B: Temp | X: Wind | Y: Rain")
    logger.info("Auto-sleep after %ds of inactivity", SLEEP_TIMEOUT)

    display = DisplayManager()
    subscriber = MqttSensorSubscriber()
    renderer = ViewRenderer(display)

    # Buttons: request our own lines on the platform chip. These are
    # disjoint from the sensor interrupt line (BCM4) that the publisher
    # owns, so both services can coexist on GPIO.
    chip = gpiodevice.find_chip_by_platform()
    button_config = {pin: gpiod.LineSettings(
        edge_detection=Edge.FALLING,
        bias=Bias.PULL_UP,
        debounce_period=timedelta(milliseconds=20)
    ) for pin in BUTTONS}
    button_lines = chip.request_lines(consumer="weather-display", config=button_config)
    poll = select.poll()
    poll.register(button_lines.fd, select.POLLIN)

    subscriber.connect()
    display.sleep()

    last_render = 0.0

    try:
        while True:
            current_time = time.time()

            if poll.poll(10):
                for event in button_lines.read_edge_events():
                    button = BUTTON_LABELS[event.line_offset]
                    logger.info(f"Button {button} pressed")
                    display.wake()
                    if button == 'A':
                        display.current_view = 'overview'
                    elif button == 'B':
                        display.current_view = 'temperature'
                    elif button == 'X':
                        display.current_view = 'wind'
                    elif button == 'Y':
                        display.current_view = 'rain'

            if display.awake and (current_time - last_render >= 1.0 / FPS):
                if not subscriber.has_data:
                    reason = "Waiting for publisher..." if subscriber.publisher_online else "Publisher offline"
                    renderer.draw_waiting(reason)
                elif display.current_view == 'overview':
                    renderer.draw_overview(subscriber)
                elif display.current_view == 'temperature':
                    renderer.draw_graph(subscriber, "TEMPERATURE", subscriber.temp_history,
                                        "°C", COLOR_YELLOW, min_val=0, max_val=40)
                elif display.current_view == 'wind':
                    renderer.draw_graph(subscriber, "WIND SPEED", subscriber.wind_speed_history,
                                        " m/s", COLOR_CYAN, min_val=0, max_val=20)
                elif display.current_view == 'rain':
                    renderer.draw_graph(subscriber, "RAIN RATE", subscriber.rain_history,
                                        " mm/s", COLOR_BLUE, min_val=0, max_val=5)

                display.render()
                last_render = current_time

            display.check_sleep()
            time.sleep(0.05)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        display.sleep()
        subscriber.close()
        logger.info("Display off")


if __name__ == "__main__":
    main()
