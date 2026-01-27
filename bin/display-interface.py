#!/usr/bin/env python3
"""
Weather HAT Display - Power Efficient Version

Features:
- Sleep mode with button wake
- Live data overview
- Historical graphs on button press
- Auto-sleep after inactivity
- Runs alongside MQTT publisher
"""
import os
import select
import time
from datetime import timedelta

import gpiod
import gpiodevice
import st7789
from fonts.ttf import ManropeBold as UserFont
from gpiod.line import Bias, Edge
from PIL import Image, ImageDraw, ImageFont

import weatherhat
from weatherhat import history

# Configuration
TEMP_OFFSET = float(os.getenv("TEMP_OFFSET", "-7.5"))
SLEEP_TIMEOUT = int(os.getenv("DISPLAY_SLEEP_TIMEOUT", "30"))  # seconds
UPDATE_INTERVAL = 2.0  # How often to read sensors

# Display settings
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240
SPI_SPEED_MHZ = 80
FPS = 5  # Lower FPS to save power

# Button configuration
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


class DisplayManager:
    """Manages display state, sleep/wake, and rendering"""

    def __init__(self):
        # Initialize display
        self.display = st7789.ST7789(
            rotation=90,
            port=0,
            cs=1,
            dc=9,
            backlight=12,
            spi_speed_hz=SPI_SPEED_MHZ * 1000 * 1000
        )
        self.display.begin()

        # Create drawing canvas (2x resolution for smoother rendering)
        self.image = Image.new("RGB", (DISPLAY_WIDTH * 2, DISPLAY_HEIGHT * 2), color=COLOR_BLACK)
        self.draw = ImageDraw.Draw(self.image)

        # Fonts
        self.font_huge = ImageFont.truetype(UserFont, 100)
        self.font_large = ImageFont.truetype(UserFont, 60)
        self.font_medium = ImageFont.truetype(UserFont, 40)
        self.font_small = ImageFont.truetype(UserFont, 28)

        # State
        self.awake = False
        self.current_view = 'overview'  # overview, temp, wind, rain, pressure
        self.last_activity = 0

    def wake(self):
        """Turn on display"""
        if not self.awake:
            self.display.set_backlight(0xFFFF)  # Full brightness
            self.awake = True
        self.last_activity = time.time()

    def sleep(self):
        """Turn off display to save power"""
        if self.awake:
            self.display.set_backlight(0)
            self.awake = False

    def check_sleep(self):
        """Auto-sleep if inactive"""
        if self.awake and (time.time() - self.last_activity) > SLEEP_TIMEOUT:
            self.sleep()

    def clear(self):
        """Clear the canvas"""
        self.draw.rectangle((0, 0, DISPLAY_WIDTH * 2, DISPLAY_HEIGHT * 2), COLOR_BLACK)

    def render(self):
        """Push canvas to display"""
        if self.awake:
            # Downscale for anti-aliasing effect
            scaled = self.image.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.LANCZOS)
            self.display.display(scaled)


class SensorDataCollector:
    """Collects and stores sensor data with history"""

    def __init__(self):
        self.sensor = weatherhat.WeatherHAT()
        self.sensor.temperature_offset = TEMP_OFFSET

        # History buffers (store 10 minutes at 2-second intervals = 300 points)
        self.temp_history = history.History(history_depth=300)
        self.pressure_history = history.History(history_depth=300)
        self.humidity_history = history.History(history_depth=300)
        self.wind_speed_history = history.WindSpeedHistory(history_depth=300)
        self.wind_dir_history = history.WindDirectionHistory(history_depth=300)
        self.rain_history = history.History(history_depth=300)
        self.light_history = history.History(history_depth=300)

        # Warm up sensors
        self.sensor.update(interval=5.0)
        time.sleep(5.0)

    def update(self):
        """Read sensors and update history"""
        self.sensor.update(interval=UPDATE_INTERVAL)

        # Store in history
        self.temp_history.append(self.sensor.temperature)
        self.pressure_history.append(self.sensor.pressure)
        self.humidity_history.append(self.sensor.relative_humidity)
        self.wind_speed_history.append(self.sensor.wind_speed)
        self.wind_dir_history.append(self.sensor.wind_direction)
        self.rain_history.append(self.sensor.rain)
        self.light_history.append(self.sensor.lux)

    def close(self):
        """Cleanup sensor resources"""
        if hasattr(self.sensor, 'close'):
            self.sensor.close()


class ViewRenderer:
    """Renders different views on the display"""

    def __init__(self, display_mgr):
        self.disp = display_mgr

    def draw_overview(self, data):
        """Main overview screen with live readings"""
        self.disp.clear()
        d = self.disp.draw

        # Title
        d.text((240, 30), "WEATHER", font=self.disp.font_large, fill=COLOR_CYAN, anchor="mm")

        # Temperature (large and prominent)
        temp_str = f"{data.sensor.temperature:.1f}°C"
        d.text((240, 140), temp_str, font=self.disp.font_huge, fill=COLOR_YELLOW, anchor="mm")

        # Grid of other readings (3 columns x 2 rows)
        readings = [
            (f"{data.sensor.humidity:.0f}%", "Humidity", COLOR_BLUE),
            (f"{data.sensor.pressure:.0f}", "hPa", COLOR_GREEN),
            (f"{data.sensor.wind_speed:.1f}", "m/s", COLOR_WHITE),
            (f"{data.wind_dir_history.latest_short_compass()}", "Wind", COLOR_WHITE),
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

        # Footer hint
        d.text((240, 460), "B:Temp X:Wind Y:Rain", font=self.disp.font_small, fill=COLOR_GREY, anchor="mm")

    def draw_graph(self, title, history_data, unit, color, min_val=None, max_val=None):
        """Draw a historical graph"""
        self.disp.clear()
        d = self.disp.draw

        # Title
        d.text((240, 30), title, font=self.disp.font_large, fill=color, anchor="mm")

        # Current value (large)
        if len(history_data._history) > 0:
            current = history_data.latest().value
            current_str = f"{current:.1f}{unit}"
            d.text((240, 100), current_str, font=self.disp.font_huge, fill=COLOR_WHITE, anchor="mm")

        # Graph area
        graph_x = 40
        graph_y = 180
        graph_w = 400
        graph_h = 240

        # Get data points
        points = history_data.history()
        if len(points) < 2:
            d.text((240, 300), "Collecting data...", font=self.disp.font_medium,
                   fill=COLOR_GREY, anchor="mm")
            return

        values = [p.value for p in points]

        # Auto-scale if not specified
        if min_val is None:
            min_val = min(values) * 0.95
        if max_val is None:
            max_val = max(values) * 1.05

        if max_val == min_val:
            max_val = min_val + 1

        # Draw axes
        d.rectangle((graph_x, graph_y, graph_x + graph_w, graph_y + graph_h), outline=COLOR_GREY)

        # Draw min/max labels
        d.text((graph_x - 10, graph_y), f"{max_val:.0f}", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="rm")
        d.text((graph_x - 10, graph_y + graph_h), f"{min_val:.0f}", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="rm")

        # Draw graph line
        num_points = len(values)
        x_step = graph_w / max(1, num_points - 1)

        for i in range(num_points - 1):
            # Normalize values to graph height
            y1 = graph_y + graph_h - ((values[i] - min_val) / (max_val - min_val) * graph_h)
            y2 = graph_y + graph_h - ((values[i + 1] - min_val) / (max_val - min_val) * graph_h)

            x1 = graph_x + (i * x_step)
            x2 = graph_x + ((i + 1) * x_step)

            d.line((x1, y1, x2, y2), fill=color, width=3)

        # Footer
        timespan = f"Last {len(points) * 2}s"
        d.text((240, 460), f"{timespan} • A:Overview", font=self.disp.font_small,
               fill=COLOR_GREY, anchor="mm")


def main():
    print("Weather HAT Display - Power Saving Mode")
    print("Press any button to wake display")
    print("A: Overview | B: Temperature | X: Wind | Y: Rain")
    print("Auto-sleep after 30s of inactivity")
    print("Press Ctrl+C to exit\n")

    # Initialize components
    display = DisplayManager()
    data_collector = SensorDataCollector()
    renderer = ViewRenderer(display)

    # Setup buttons
    chip = gpiodevice.find_chip_by_platform()
    button_config = {pin: gpiod.LineSettings(
        edge_detection=Edge.FALLING,
        bias=Bias.PULL_UP,
        debounce_period=timedelta(milliseconds=20)
    ) for pin in BUTTONS}

    button_lines = chip.request_lines(consumer="weather-display", config=button_config)
    poll = select.poll()
    poll.register(button_lines.fd, select.POLLIN)

    # Start in sleep mode
    display.sleep()

    last_update = 0
    last_render = 0

    try:
        while True:
            current_time = time.time()

            # Check for button presses
            if poll.poll(10):
                for event in button_lines.read_edge_events():
                    button = BUTTON_LABELS[event.line_offset]
                    print(f"Button {button} pressed")

                    # Wake display
                    display.wake()

                    # Change view based on button
                    if button == 'A':
                        display.current_view = 'overview'
                    elif button == 'B':
                        display.current_view = 'temperature'
                    elif button == 'X':
                        display.current_view = 'wind'
                    elif button == 'Y':
                        display.current_view = 'rain'

            # Update sensor data
            if current_time - last_update >= UPDATE_INTERVAL:
                data_collector.update()
                last_update = current_time

            # Render if awake
            if display.awake and (current_time - last_render >= 1.0 / FPS):
                if display.current_view == 'overview':
                    renderer.draw_overview(data_collector)
                elif display.current_view == 'temperature':
                    renderer.draw_graph(
                        "TEMPERATURE",
                        data_collector.temp_history,
                        "°C",
                        COLOR_YELLOW,
                        min_val=0,
                        max_val=40
                    )
                elif display.current_view == 'wind':
                    renderer.draw_graph(
                        "WIND SPEED",
                        data_collector.wind_speed_history,
                        " m/s",
                        COLOR_CYAN,
                        min_val=0,
                        max_val=20
                    )
                elif display.current_view == 'rain':
                    renderer.draw_graph(
                        "RAIN RATE",
                        data_collector.rain_history,
                        " mm/s",
                        COLOR_BLUE,
                        min_val=0,
                        max_val=5
                    )

                display.render()
                last_render = current_time

            # Check for auto-sleep
            display.check_sleep()

            # Small sleep to prevent CPU spinning
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        display.sleep()
        data_collector.close()
        print("Display off")


if __name__ == "__main__":
    main()
