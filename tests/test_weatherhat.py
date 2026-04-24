"""Tests for the core WeatherHAT library.

Adapted from upstream pimoroni/weatherhat-python test_setup.py.
Verifies constructor wiring and sensor value propagation using
mocked hardware backends.
"""


def test_constructor_wires_i2c_devices(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """WeatherHAT constructor initializes BME280, LTR559, and IOE on the correct bus/address."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    bus = smbus2.SMBus(1)
    bme280.BME280.assert_called_once_with(i2c_dev=bus)
    ltr559.LTR559.assert_called_once_with(i2c_dev=bus)
    ioe.IOE.assert_called_once_with(i2c_addr=0x12)

    sensor.close()


def test_gpio_chip_and_interrupt_setup(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """Constructor finds the GPIO chip and requests the interrupt line."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    gpiodevice.find_chip_by_platform.assert_called_once()
    chip = gpiodevice.find_chip_by_platform.return_value
    chip.request_lines.assert_called_once()

    # Verify interrupt pin 4 is in the request
    call_kwargs = chip.request_lines.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert 4 in config, "Interrupt pin 4 should be in the line request config"

    sensor.close()


def test_sensor_values_propagate(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """Sensor read values propagate correctly through update()."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    bus = smbus2.SMBus(1)

    # Configure mock return values
    bme280.BME280(i2c_dev=bus).get_temperature.return_value = 20.0
    bme280.BME280(i2c_dev=bus).get_pressure.return_value = 1013.25
    bme280.BME280(i2c_dev=bus).get_humidity.return_value = 60.0
    ltr559.LTR559(i2c_dev=bus).get_lux.return_value = 100.0
    ioe.IOE(i2c_addr=0x12).input.return_value = 2.5  # ~180 degrees (South)

    sensor.temperature_offset = 5.0
    sensor.update()

    assert sensor.device_temperature == 20.0
    assert sensor.temperature == 25.0  # 20.0 + 5.0 offset
    assert sensor.pressure == 1013.25
    assert sensor.humidity == 60.0
    assert sensor.lux == 100.0

    sensor.close()


def test_wind_direction_mapping(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """Wind vane ADC voltage maps to correct compass degrees."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    bus = smbus2.SMBus(1)
    bme280.BME280(i2c_dev=bus).get_temperature.return_value = 20.0
    bme280.BME280(i2c_dev=bus).get_pressure.return_value = 1013.25
    bme280.BME280(i2c_dev=bus).get_humidity.return_value = 60.0
    ltr559.LTR559(i2c_dev=bus).get_lux.return_value = 100.0

    # Test each wind direction voltage -> degrees mapping
    for voltage, expected_degrees in weatherhat.wind_direction_to_degrees.items():
        ioe.IOE(i2c_addr=0x12).input.return_value = voltage
        sensor.update()
        assert sensor.wind_direction == expected_degrees, f"Voltage {voltage}V should map to {expected_degrees}°, got {sensor.wind_direction}°"

    sensor.close()


def test_humidity_compensation(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """Relative humidity is compensated based on temperature offset."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    bus = smbus2.SMBus(1)
    bme280.BME280(i2c_dev=bus).get_temperature.return_value = 20.0
    bme280.BME280(i2c_dev=bus).get_pressure.return_value = 1013.25
    bme280.BME280(i2c_dev=bus).get_humidity.return_value = 60.0
    ltr559.LTR559(i2c_dev=bus).get_lux.return_value = 100.0
    ioe.IOE(i2c_addr=0x12).input.return_value = 2.5

    sensor.temperature_offset = 5.0
    sensor.update()

    # Dewpoint = 20.0 - ((100 - 60) / 5) = 12.0
    # Relative humidity = 100 - (5 * (25.0 - 12.0)) - 20 = 100 - 65 - 20 = 15.0
    assert sensor.relative_humidity == 15.0
    assert sensor.dewpoint == 12.0

    sensor.close()


def test_degrees_to_cardinal(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """degrees_to_cardinal returns correct compass direction strings."""
    import weatherhat

    sensor = weatherhat.WeatherHAT()

    assert sensor.degrees_to_cardinal(0) == "North"
    assert sensor.degrees_to_cardinal(90) == "East"
    assert sensor.degrees_to_cardinal(180) == "South"
    assert sensor.degrees_to_cardinal(270) == "West"
    assert sensor.degrees_to_cardinal(45) == "North East"

    sensor.close()


def test_context_manager(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """WeatherHAT works as a context manager for clean resource teardown."""
    import weatherhat

    with weatherhat.WeatherHAT() as sensor:
        assert sensor is not None
        assert sensor._polling is True

    # After exiting context, polling should be stopped
    assert sensor._polling is False


def test_close_is_safe_when_init_fails_early(gpiod, gpiodevice, ioe, bme280, ltr559, smbus2):
    """close()/__del__ must not raise if __init__ failed before setting _polling.

    Regression: a user report showed `AttributeError: 'WeatherHAT' object has
    no attribute '_poll_thread'` masking the real error (EBUSY on the GPIO
    line request) whenever two processes tried to instantiate WeatherHAT.
    close() must tolerate partially-initialized instances.
    """
    import weatherhat

    # Make SMBus raise so __init__ fails before _polling is assigned
    smbus2.SMBus.side_effect = OSError("simulated I2C init failure")

    try:
        weatherhat.WeatherHAT()
    except OSError:
        pass  # expected — we want the real error to surface
    # Reaching this point means __del__ (which runs as the instance is
    # garbage-collected) did not raise. Explicitly construct a bare
    # instance and exercise close() directly to be thorough.
    bare = weatherhat.WeatherHAT.__new__(weatherhat.WeatherHAT)
    bare.close()  # must not raise
