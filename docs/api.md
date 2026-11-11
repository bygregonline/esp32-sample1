# HTTP API

The `/` route serves a responsive dashboard. It fetches `/api/status` every two
seconds and displays local time, device IP, battery, temperature, humidity,
pressure, GPS coordinates, weather, moon phase, the sensor countdown, and recent
events.

The C, MicroPython, and Rust firmware versions expose the same routes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | HTML status panel |
| GET | `/moon.bmp` | Current phase image as a 64×64 grayscale BMP |
| GET | `/api/status` | Complete telemetry snapshot |
| GET | `/api/sensors` | Latest sensor readings |
| GET | `/api/weather` | Forecast data |
| POST | `/api/config/interval` | Sensor update interval |
| POST | `/api/config/display` | Visible display sections |
| POST | `/wifi` | Wi-Fi credentials |

For request and response examples, see the [full API reference](https://github.com/bygregonline/esp32-sample1/blob/master/API.md).

The status and sensor payloads include `pressure_hpa`, `bmp280_valid`, `moon_phase` (0=new, 0.5=full), `moon_illumination_percent`, GPS latitude/longitude, `local_time`, and recent `events`. Missing hardware or unavailable forecast values are `null`. The moon endpoint renders and reuses a compact 64×64 BMP buffer from the current phase. Display configuration accepts the `pressure` and `moon` keys in addition to battery, DHT, GPS, and weather. The parallel BLE GATT protocol is documented in [Bluetooth Low Energy](ble.md).
