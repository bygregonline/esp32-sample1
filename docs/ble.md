# Bluetooth Low Energy

The C / ESP-IDF, Rust / ESP-IDF, and MicroPython firmware advertise as
`ESP32-Monitor` and expose the same read-only GATT service. A BLE central chooses
the serialization by reading one characteristic. Values are generated from the
current monitor snapshot; a long read can be used when the value exceeds the
central's negotiated ATT payload size.

| UUID | Characteristic | Value |
|------|----------------|-------|
| `0xFFA0` | Service | ESP32 monitor snapshot service |
| `0xFFA1` | JSON | Compact JSON telemetry object |
| `0xFFA2` | Text | `key=value` telemetry lines |
| `0xFFA3` | YAML | YAML telemetry mapping |
| `0xFFA4` | XML | `<monitor>` telemetry document |

Each format uses the same compact field names: `time`, `ip`, `wifi`, `ssid`,
`battery_v`, `temp_c`, `hum_pct`, `pressure_hpa`, `lat`, `lon`, `forecast`,
`wx_c`, `wx_hum_pct`, `wx_min_c`, `wx_max_c`, `rain_pct`, `moon`,
`moon_illum_pct`, `interval_s`, `remaining_s`, and `event`. These represent local
time, network state, sensor values, GPS coordinates, current/daily forecast,
precipitation chance, lunar phase/illumination, the sensor-cycle countdown, and
the latest event. Missing values are JSON/YAML `null` and empty XML elements.
Values fit within the standard 512-byte GATT attribute limit. The HTTP endpoints remain available in parallel, including
`GET /api/status`, `GET /api/sensors`, and `GET /api/weather`.

| Fields | Meaning |
|--------|---------|
| `time`, `ip`, `wifi`, `ssid` | Local clock, network address, connection state, and network name |
| `battery_v`, `temp_c`, `hum_pct`, `pressure_hpa` | Battery voltage, DHT22 temperature/humidity, and BMP280 pressure in hPa |
| `lat`, `lon` | GPS degrees; null until a valid fix |
| `forecast`, `wx_c`, `wx_hum_pct`, `wx_min_c`, `wx_max_c`, `rain_pct` | Weather summary, current conditions, daily range, and precipitation chance |
| `moon`, `moon_illum_pct` | Lunar phase fraction (0 new, 0.5 full) and illumination percentage |
| `interval_s`, `remaining_s`, `event` | Sensor refresh cadence/countdown and latest logger entry |

For a BLE client, discover service `FFA0` and read the format characteristic it
needs. Use the characteristic UUID to select JSON, text, YAML, or XML. The
wire payload uses UTF-8; JSON is the recommended choice for machines, while the
other formats are intended for quick inspection or clients with a fixed parser.

The peripheral does not require pairing for these read-only telemetry values.
Builds verify that the stack and GATT service compile; an actual phone/central
connection still needs to be checked on physical hardware.
