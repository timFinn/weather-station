"""Tests for I2C bus recovery module."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weatherhat import i2c_recovery


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Reset the rate-limiting state between tests."""
    i2c_recovery._last_recovery_time = 0.0
    yield


@pytest.fixture()
def mock_script_exists():
    """Pretend the recovery script exists on disk."""
    with patch("os.path.isfile", return_value=True):
        yield


class TestRateLimiting:
    def test_first_call_not_rate_limited(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
            assert i2c_recovery.attempt_i2c_recovery() is True

    def test_second_call_rate_limited(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
            i2c_recovery.attempt_i2c_recovery()
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_force_bypasses_rate_limit(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
            i2c_recovery.attempt_i2c_recovery()
            assert i2c_recovery.attempt_i2c_recovery(force=True) is True


class TestScriptExecution:
    def test_missing_script_returns_false(self):
        with patch("os.path.isfile", return_value=False):
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_successful_recovery(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Bus recovered\n", stderr="")
            assert i2c_recovery.attempt_i2c_recovery() is True
            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0] == ["sudo", i2c_recovery.RECOVERY_SCRIPT]

    def test_failed_recovery(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="bus still stuck")
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_prerequisites_not_met(self, mock_script_exists):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="pinctrl not found")
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_timeout(self, mock_script_exists):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=15)):
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_sudo_not_found(self, mock_script_exists):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert i2c_recovery.attempt_i2c_recovery() is False

    def test_unexpected_error(self, mock_script_exists):
        with patch("subprocess.run", side_effect=OSError("bus error")):
            assert i2c_recovery.attempt_i2c_recovery() is False


class TestConstants:
    def test_recovery_script_path(self):
        assert i2c_recovery.RECOVERY_SCRIPT.endswith("scripts/i2c-bus-recovery.sh")

    def test_min_interval(self):
        assert i2c_recovery.MIN_RECOVERY_INTERVAL == 30
