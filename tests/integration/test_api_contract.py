"""Integration tests — API contract validation.

These tests can run against a live device OR against a local mock server.
Set ESP32_IP to point to a real device, or leave unset to skip live tests.

    # Run against a live device
    ESP32_IP=192.168.1.42 pytest tests/integration/

    # Run only the mock-server tests (no hardware)
    pytest tests/integration/
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
import requests

# ── Configuration ─────────────────────────────────────────────────────────
DEVICE_IP = os.environ.get("ESP32_IP")
LIVE = bool(DEVICE_IP)
BASE_URL = f"http://{DEVICE_IP}" if LIVE else "http://127.0.0.1:18180"

# ── Minimal mock server (mirrors the embedded server JSON schema) ──────────

_mock_state: dict[str, Any] = {
    "sensor_interval": 10,
    "display_mask": 0x0F,
}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silence access log
        pass

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):  # noqa: N802
        if self.path == "/api/status":
            self._send_json(200, _full_status())
        elif self.path == "/api/sensors":
            self._send_json(200, _sensors_payload())
        elif self.path == "/api/weather":
            self._send_json(200, _weather_payload())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Mock ESP32</body></html>")
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        body = self._read_body()
        if self.path == "/api/config/interval":
            try:
                data = json.loads(body)
                iv = int(data.get("interval_seconds", 0))
                if 5 <= iv <= 300:
                    _mock_state["sensor_interval"] = iv
                    self._send_json(200, {"ok": True, "interval_seconds": iv})
                else:
                    self._send_json(400, {"ok": False, "error": "fuera de rango"})
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
        elif self.path == "/api/config/display":
            try:
                data = json.loads(body)
                mask = _mock_state["display_mask"]
                for key, bit in (("battery", 1), ("dht", 2), ("gps", 4), ("weather", 8)):
                    if key in data:
                        mask = (mask | bit) if data[key] else (mask & ~bit & 0xFF)
                _mock_state["display_mask"] = mask
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "display_mask": mask,
                        "battery": bool(mask & 1),
                        "dht": bool(mask & 2),
                        "gps": bool(mask & 4),
                        "weather": bool(mask & 8),
                    },
                )
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
        elif self.path == "/wifi":
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"error": "not found"})


def _sensors_payload() -> dict:
    return {
        "battery_v": 12.34,
        "temperature_c": 24.1,
        "humidity_percent": 55.0,
        "dht_valid": True,
        "gps_fix": True,
        "latitude": 19.4326,
        "longitude": -99.1332,
        "satellites": 9,
        "last_read_ms": 1000,
        "interval_seconds": _mock_state["sensor_interval"],
        "remaining_seconds": 5,
    }


def _weather_payload() -> dict:
    return {
        "available": True,
        "summary": "SOLEADO",
        "weather_code": 0,
        "current_temperature_c": 22.5,
        "current_humidity_percent": 48.0,
        "minimum_temperature_c": 15.0,
        "maximum_temperature_c": 28.0,
        "precipitation_probability": 5,
        "age_seconds": 60,
        "stale": False,
    }


def _full_status() -> dict:
    return {
        "sensors": {
            "battery_v": 12.34,
            "temperature_c": 24.1,
            "humidity_percent": 55.0,
            "dht_valid": True,
            "last_read_ms": 1000,
        },
        "gps": {
            "fix": True,
            "latitude": 19.4326,
            "longitude": -99.1332,
            "satellites": 9,
        },
        "wifi": {"connected": True, "ssid": "TestNet", "ip": "192.168.1.42"},
        "refresh": {
            "interval_seconds": _mock_state["sensor_interval"],
            "weather_interval_seconds": 300,
            "remaining_seconds": 5,
        },
        "display_mask": _mock_state["display_mask"],
        "weather": _weather_payload(),
    }


@pytest.fixture(scope="session", autouse=True)
def mock_server():
    if LIVE:
        yield  # use real device
        return
    server = HTTPServer(("127.0.0.1", 18180), MockHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)
    yield server
    server.shutdown()


# ── Test cases ────────────────────────────────────────────────────────────


class TestStatusEndpoint:
    def test_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/status", timeout=5)
        assert r.status_code == 200

    def test_content_type_json(self):
        r = requests.get(f"{BASE_URL}/api/status", timeout=5)
        assert "application/json" in r.headers.get("Content-Type", "")

    def test_sensors_block_present(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert "sensors" in data
        assert "battery_v" in data["sensors"]

    def test_gps_block_present(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert "gps" in data
        assert "fix" in data["gps"]

    def test_wifi_block_present(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert "wifi" in data
        assert "connected" in data["wifi"]

    def test_refresh_block_present(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert "refresh" in data
        assert "interval_seconds" in data["refresh"]
        assert "remaining_seconds" in data["refresh"]

    def test_weather_block_present(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert "weather" in data
        assert "available" in data["weather"]

    def test_display_mask_integer(self):
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert isinstance(data["display_mask"], int)


class TestSensorsEndpoint:
    def test_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/sensors", timeout=5)
        assert r.status_code == 200

    def test_required_fields(self):
        data = requests.get(f"{BASE_URL}/api/sensors", timeout=5).json()
        for field in ["battery_v", "dht_valid", "gps_fix", "interval_seconds", "remaining_seconds"]:
            assert field in data, f"missing field: {field}"

    def test_battery_is_numeric(self):
        data = requests.get(f"{BASE_URL}/api/sensors", timeout=5).json()
        assert isinstance(data["battery_v"], int | float)


class TestWeatherEndpoint:
    def test_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/weather", timeout=5)
        assert r.status_code == 200

    def test_available_is_bool(self):
        data = requests.get(f"{BASE_URL}/api/weather", timeout=5).json()
        assert isinstance(data["available"], bool)

    def test_stale_is_bool(self):
        data = requests.get(f"{BASE_URL}/api/weather", timeout=5).json()
        assert isinstance(data["stale"], bool)


class TestConfigInterval:
    def test_valid_interval_accepted(self):
        r = requests.post(
            f"{BASE_URL}/api/config/interval",
            json={"interval_seconds": 30},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["interval_seconds"] == 30

    def test_interval_reflected_in_status(self):
        requests.post(f"{BASE_URL}/api/config/interval", json={"interval_seconds": 45}, timeout=5)
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert data["refresh"]["interval_seconds"] == 45

    def test_below_min_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/config/interval", json={"interval_seconds": 4}, timeout=5
        )
        assert r.json()["ok"] is False

    def test_above_max_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/config/interval", json={"interval_seconds": 301}, timeout=5
        )
        assert r.json()["ok"] is False

    def test_boundary_min(self):
        r = requests.post(
            f"{BASE_URL}/api/config/interval", json={"interval_seconds": 5}, timeout=5
        )
        assert r.json()["ok"] is True

    def test_boundary_max(self):
        r = requests.post(
            f"{BASE_URL}/api/config/interval", json={"interval_seconds": 300}, timeout=5
        )
        assert r.json()["ok"] is True


class TestConfigDisplay:
    def test_hide_gps_and_weather(self):
        r = requests.post(
            f"{BASE_URL}/api/config/display",
            json={"battery": True, "dht": True, "gps": False, "weather": False},
            timeout=5,
        )
        data = r.json()
        assert data["ok"] is True
        assert data["gps"] is False
        assert data["weather"] is False
        assert data["battery"] is True

    def test_show_all(self):
        r = requests.post(
            f"{BASE_URL}/api/config/display",
            json={"battery": True, "dht": True, "gps": True, "weather": True},
            timeout=5,
        )
        data = r.json()
        assert data["display_mask"] == 15

    def test_mask_reflected_in_status(self):
        requests.post(
            f"{BASE_URL}/api/config/display",
            json={"battery": True, "dht": True, "gps": True, "weather": True},
            timeout=5,
        )
        data = requests.get(f"{BASE_URL}/api/status", timeout=5).json()
        assert data["display_mask"] == 15

    def test_partial_update_preserves_others(self):
        # Start with all visible
        requests.post(
            f"{BASE_URL}/api/config/display",
            json={"battery": True, "dht": True, "gps": True, "weather": True},
            timeout=5,
        )
        # Hide only GPS
        r = requests.post(f"{BASE_URL}/api/config/display", json={"gps": False}, timeout=5)
        data = r.json()
        assert data["battery"] is True
        assert data["dht"] is True
        assert data["gps"] is False
        assert data["weather"] is True
