# MicroPython

The MicroPython version targets a dual-USB-C ESP32-S3 N16R8 development board. GPIO assignments follow the ESP32-S3-DevKitC-1 reference; verify the printed pin labels on the purchased carrier board. It includes the display drivers, GPS parser, and BMP280 I²C driver in the repository. Its root page auto-refreshes from the HTTP API, and its BLE GATT peripheral makes the current snapshot readable as JSON, text, YAML, or XML. Host-side development tools are installed through `uv`; the board runs standard MicroPython modules. BMP280 uses I²C1 SDA GPIO1 and SCL GPIO2.

```sh
cd python
./scripts/install-deps.sh
./scripts/build.sh
./scripts/deploy.sh
```

The MkDocs [Python source reference](reference/python.md) is generated from module docstrings and signatures by `mkdocstrings-python` without importing ESP32-only hardware modules.

See the [MicroPython README](https://github.com/bygregonline/esp32-sample1/blob/master/python/README.md) for wiring and calibration.
