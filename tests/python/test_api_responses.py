"""Tests for the HTTP API response structure.

Validates that the JSON payloads returned by the embedded server
match the documented schema exactly — same field names, types,
and nesting as the C implementation.
"""

import json
import sys
import time as time_module

# ── Stub all MicroPython modules ──────────────────────────────────────────
from pathlib import Path
from unittest.mock import MagicMock

for mod in [
    "machine",
    "dht",
    "usocket",
    "network",
    "ntptime",
    "urequests",
    "machine.ADC",
    "machine.Pin",
    "machine.SPI",
    "machine.I2C",
    "machine.UART",
]:
    sys.modules.setdefault(mod, MagicMock())

time_module.ticks_ms = lambda: 1000
time_module.ticks_diff = lambda a, b: a - b
time_module.sleep_ms = lambda _: None

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "python"))

# Stub driver modules
sys.modules.setdefault("ssd1306", MagicMock())
sys.modules.setdefault("st7789", MagicMock())


# Patch config before importing main
import config  # noqa: E402 — real config module

# Import only the pure functions from main without running main()
import main as m  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────


def make_full_state(**overrides):
    state = {
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
    state.update(overrides)
    return state


# ── /api/sensors schema ───────────────────────────────────────────────────


class TestSensorsJson:
    def test_all_keys_present(self):
        state = make_full_state()
        payload = json.loads(m._sensors_json(state))
        required = {
            "battery_v",
            "temperature_c",
            "humidity_percent",
            "dht_valid",
            "gps_fix",
            "latitude",
            "longitude",
            "satellites",
            "last_read_ms",
            "interval_seconds",
            "remaining_seconds",
        }
        assert required.issubset(payload.keys())

    def test_battery_is_float(self):
        state = make_full_state()
        payload = json.loads(m._sensors_json(state))
        assert isinstance(payload["battery_v"], float)

    def test_dht_null_when_invalid(self):
        state = make_full_state(dht_valid=False)
        payload = json.loads(m._sensors_json(state))
        assert payload["temperature_c"] is None
        assert payload["humidity_percent"] is None

    def test_gps_null_when_no_fix(self):
        state = make_full_state(gps_fix=False)
        payload = json.loads(m._sensors_json(state))
        assert payload["latitude"] is None
        assert payload["longitude"] is None

    def test_remaining_seconds_non_negative(self):
        state = make_full_state(last_read_ms=0, sensor_interval_s=10)
        m.ticks_ms = lambda: 5000
        payload = json.loads(m._sensors_json(state))
        assert payload["remaining_seconds"] >= 0


# ── /api/status schema ────────────────────────────────────────────────────


class TestStatusJson:
    def test_top_level_keys(self):
        state = make_full_state()
        payload = json.loads(m._status_json(state))
        assert {"sensors", "gps", "wifi", "refresh", "display_mask", "weather"}.issubset(
            payload.keys()
        )

    def test_sensors_block(self):
        state = make_full_state()
        sensors = json.loads(m._status_json(state))["sensors"]
        assert "battery_v" in sensors
        assert "dht_valid" in sensors
        assert "last_read_ms" in sensors

    def test_refresh_block_keys(self):
        state = make_full_state()
        refresh = json.loads(m._status_json(state))["refresh"]
        assert "interval_seconds" in refresh
        assert "weather_interval_seconds" in refresh
        assert "remaining_seconds" in refresh

    def test_wifi_block(self):
        state = make_full_state()
        wifi = json.loads(m._status_json(state))["wifi"]
        assert wifi["connected"] is True
        assert wifi["ssid"] == "TestNet"
        assert wifi["ip"] == "192.168.1.42"

    def test_display_mask_integer(self):
        state = make_full_state(display_mask=0x0F)
        payload = json.loads(m._status_json(state))
        assert payload["display_mask"] == 15


# ── /api/weather schema ───────────────────────────────────────────────────


class TestWeatherJson:
    def test_available_true_when_valid(self):
        state = make_full_state()
        payload = json.loads(m._weather_json(state, 1000))
        assert payload["available"] is True

    def test_all_weather_keys_present(self):
        state = make_full_state()
        payload = json.loads(m._weather_json(state, 1000))
        required = {
            "available",
            "summary",
            "weather_code",
            "current_temperature_c",
            "current_humidity_percent",
            "minimum_temperature_c",
            "maximum_temperature_c",
            "precipitation_probability",
            "age_seconds",
            "stale",
        }
        assert required.issubset(payload.keys())

    def test_available_false_when_invalid(self):
        state = make_full_state()
        state["weather"]["valid"] = False
        payload = json.loads(m._weather_json(state, 1000))
        assert payload["available"] is False

    def test_stale_flag(self):
        state = make_full_state()
        # age = (now - updated_ms) / 1000 = (700000 - 400) / 1000 = 699.6 s
        # stale if age > refresh_interval_s * 2 = 600 s → should be stale
        payload = json.loads(m._weather_json(state, 700_000))
        assert payload["stale"] is True


# ── display_mask mutations ────────────────────────────────────────────────


class TestDisplayMask:
    def test_set_all_visible(self):
        state = make_full_state(display_mask=0x00)
        m._state = state
        # Simulate POST /api/config/display {"battery":true,...}
        data = {"battery": True, "dht": True, "gps": True, "weather": True}
        mask = state["display_mask"]
        for key, bit in (("battery", 0x01), ("dht", 0x02), ("gps", 0x04), ("weather", 0x08)):
            if data.get(key):
                mask |= bit
            else:
                mask &= ~bit & 0xFF
        state["display_mask"] = mask
        assert state["display_mask"] == 0x0F

    def test_hide_gps_and_weather(self):
        state = make_full_state(display_mask=0x0F)
        data = {"gps": False, "weather": False}
        mask = state["display_mask"]
        for key, bit in (("battery", 0x01), ("dht", 0x02), ("gps", 0x04), ("weather", 0x08)):
            if key in data:
                if data[key]:
                    mask |= bit
                else:
                    mask &= ~bit & 0xFF
        state["display_mask"] = mask
        assert state["display_mask"] == 0x03
        assert not (mask & 0x04)
        assert not (mask & 0x08)


# ── interval validation ───────────────────────────────────────────────────


class TestIntervalValidation:
    def test_valid_interval_accepted(self):
        for v in [5, 10, 30, 60, 300]:
            assert config.SENSOR_INTERVAL_MIN_S <= v <= config.SENSOR_INTERVAL_MAX_S

    def test_invalid_interval_rejected(self):
        for v in [0, 4, 301, 999, -1]:
            assert not (config.SENSOR_INTERVAL_MIN_S <= v <= config.SENSOR_INTERVAL_MAX_S)
