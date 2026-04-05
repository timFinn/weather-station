"""Shared pytest fixtures for mocking weather station hardware dependencies.

Adapted from upstream pimoroni/weatherhat-python test fixtures.

Hardware mocks are injected into sys.modules at two levels:
1. Module level — baseline MagicMocks so collection-time imports succeed
   (e.g. ``from weatherhat.history import History`` won't fail on ``import gpiod``)
2. Per-test fixtures — fresh MagicMocks with specific configuration for tests
   that need to assert on constructor calls, return values, etc.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Baseline hardware mocks — active at collection time and between tests.
_HARDWARE_MODULES = ["gpiod", "gpiod.line", "gpiodevice", "ioexpander", "bme280", "ltr559", "smbus2", "st7789"]
for _mod in _HARDWARE_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _restore_baseline_mocks():
    """Replace hardware mocks with fresh MagicMocks (clears call history)."""
    for mod in _HARDWARE_MODULES:
        sys.modules[mod] = MagicMock()


@pytest.fixture(scope="function", autouse=True)
def cleanup():
    """Remove weatherhat from sys.modules and restore fresh hardware mocks.

    Ensures the module is fully re-imported with clean state
    for every test function.
    """
    yield None
    for mod in list(sys.modules.keys()):
        if mod.startswith("weatherhat"):
            del sys.modules[mod]
    _restore_baseline_mocks()


@pytest.fixture(scope="function")
def smbus2():
    """Mock smbus2 module with fresh state."""
    smbus2 = MagicMock()
    smbus2.i2c_msg.read().__iter__.return_value = [0b00000000]
    sys.modules["smbus2"] = smbus2
    yield smbus2


@pytest.fixture(scope="function")
def gpiod():
    """Mock gpiod module and its submodules with fresh state."""
    sys.modules["gpiod"] = MagicMock()
    sys.modules["gpiod.line"] = MagicMock()
    yield sys.modules["gpiod"]


@pytest.fixture(scope="function")
def gpiodevice():
    """Mock gpiodevice module.

    Provides a real fd via os.pipe() so the polling thread's
    select.poll().register() doesn't raise ValueError.
    """
    gpiodevice = MagicMock()
    r_fd, w_fd = os.pipe()
    mock_lines = MagicMock()
    mock_lines.fd = r_fd
    gpiodevice.find_chip_by_platform.return_value.request_lines.return_value = mock_lines
    sys.modules["gpiodevice"] = gpiodevice
    yield gpiodevice
    os.close(r_fd)
    os.close(w_fd)


@pytest.fixture(scope="function")
def bme280():
    """Mock pimoroni BME280 module with fresh state."""
    bme280 = MagicMock()
    sys.modules["bme280"] = bme280
    yield bme280


@pytest.fixture(scope="function")
def ltr559():
    """Mock LTR559 light sensor module with fresh state."""
    ltr559 = MagicMock()
    sys.modules["ltr559"] = ltr559
    yield ltr559


@pytest.fixture(scope="function")
def ioe():
    """Mock IO Expander module with fresh state."""
    ioe = MagicMock()
    sys.modules["ioexpander"] = ioe
    yield ioe


@pytest.fixture(scope="function")
def st7789():
    """Mock ST7789 display module with fresh state."""
    st7789 = MagicMock()
    sys.modules["st7789"] = st7789
    yield st7789


@pytest.fixture(scope="function")
def hardware(smbus2, gpiod, gpiodevice, bme280, ltr559, ioe, st7789):
    """Convenience fixture that activates all hardware mocks at once.

    Returns a dict of all mock modules for easy access.
    """
    return {
        "smbus2": smbus2,
        "gpiod": gpiod,
        "gpiodevice": gpiodevice,
        "bme280": bme280,
        "ltr559": ltr559,
        "ioe": ioe,
        "st7789": st7789,
    }
