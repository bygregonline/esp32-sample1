# HTTP API

The C, MicroPython, and Rust firmware versions expose the same routes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | HTML status panel |
| GET | `/api/status` | Complete telemetry snapshot |
| GET | `/api/sensors` | Latest sensor readings |
| GET | `/api/weather` | Forecast data |
| POST | `/api/config/interval` | Sensor update interval |
| POST | `/api/config/display` | Visible display sections |
| POST | `/wifi` | Wi-Fi credentials |

For request and response examples, see the [full API reference](https://github.com/bygregonline/esp32-sample1/blob/master/API.md).
