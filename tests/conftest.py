"""
Shared pytest configuration and MicroPython module stubs.

All tests under tests/python/ and tests/integration/ share these
fixtures and the MicroPython stub layer so individual test files
don't need to repeat the boilerplate.
"""

from __future__ import annotations

import sys
import time as time_module
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent

# ── MicroPython module stubs ──────────────────────────────────────────────
# Register lightweight stubs before any firmware module is imported.
# Tests that need finer control can override these with their own mocks.


def _install_micropython_stubs() -> None:
    """Install stubs for every MicroPython-only import used in python/."""

    # Add MicroPython's clock helpers without hiding CPython's monotonic().
    time_module.ticks_ms = lambda: 0
    time_module.ticks_diff = lambda a, b: a - b
    time_module.sleep_ms = lambda _: None

    # machine peripherals
    machine_stub = MagicMock()
    for submod in [
        "machine",
        "machine.ADC",
        "machine.Pin",
        "machine.SPI",
        "machine.I2C",
        "machine.UART",
    ]:
        sys.modules.setdefault(submod, machine_stub)

    # dht
    sys.modules.setdefault("dht", MagicMock())

    # network / ntptime / urequests
    sys.modules.setdefault("network", MagicMock())
    sys.modules.setdefault("ntptime", MagicMock())
    sys.modules.setdefault("urequests", MagicMock())

    # usocket
    sys.modules.setdefault("usocket", MagicMock())

    # Display drivers
    sys.modules.setdefault("ssd1306", MagicMock())
    sys.modules.setdefault("st7789", MagicMock())

    # GPS parser (real module — add python/ to path)
    firmware_path = str(ROOT / "python")
    if firmware_path not in sys.path:
        sys.path.insert(0, firmware_path)


_install_micropython_stubs()

# ── Markers ───────────────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires ESP32_IP env var")
    config.addinivalue_line("markers", "slow: slow test (>5 s)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    import os

    if not os.environ.get("ESP32_IP"):
        skip_live = pytest.mark.skip(reason="set ESP32_IP to run live tests")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_ticks(monkeypatch: pytest.MonkeyPatch):
    """Control ticks_ms() return value in tests."""
    _t = {"ms": 0}

    def _ticks_ms():
        return _t["ms"]

    def _ticks_diff(a: int, b: int) -> int:
        return a - b

    time_mod = sys.modules["time"]
    monkeypatch.setattr(time_mod, "ticks_ms", _ticks_ms)
    monkeypatch.setattr(time_mod, "ticks_diff", _ticks_diff)
    return _t


@pytest.fixture()
def clean_nmea_parser():
    """Return a freshly constructed NMEAParser."""
    from gps import NMEAParser  # noqa: PLC0415

    return NMEAParser()


@pytest.fixture()
def full_state():
    """Return a populated _state dict matching the firmware schema."""
    return {
        "battery_v": 12.5,
        "temperature_c": 24.1,
        "humidity_percent": 55.0,
        "dht_valid": True,
        "gps_fix": True,
        "latitude": 19.4326,
        "longitude": -99.1332,
        "satellites": 9,
        "last_read_ms": 500,
        "sensor_interval_s": 10,
        "next_refresh_ms": 0,
        "refresh_interval_s": 300,
        "display_mask": 0x0F,
        "wifi_connected": True,
        "wifi_ssid": "TestNet",
        "ip_address": "192.168.1.42",
        "_last_display_ms": 0,
        "_last_dht_ms": 0,
        "_last_weather_lat": None,
        "_last_weather_lon": None,
        "weather": {
            "valid": True,
            "weather_code": 0,
            "summary": "SOLEADO",
            "current_temperature_c": 22.5,
            "current_humidity_percent": 48.0,
            "minimum_temperature_c": 15.0,
            "maximum_temperature_c": 28.0,
            "precipitation_probability": 5,
            "updated_ms": 400,
        },
    }
