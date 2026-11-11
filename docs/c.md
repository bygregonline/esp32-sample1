# C / ESP-IDF

The C implementation is the reference firmware for a dual-USB-C ESP32-S3 N16R8 development board. GPIO assignments follow the ESP32-S3-DevKitC-1 reference; verify the printed pin labels on the purchased carrier board. It uses ESP-IDF 5.x, FreeRTOS, the ESP HTTP server, and NimBLE. The root page is a dashboard that refreshes the status API every two seconds; the GATT server exposes JSON, text, YAML, and XML snapshots. Its GPIO map lives in `c/main/config.h`; BMP280 support uses the pinned `esp-idf-lib/bmp280` component on I²C1 (GPIO1/2).

```sh
cd c
./scripts/install-deps.sh
./scripts/build.sh
```

The build creates `c/build/esp32_monitor_c.bin`. Connect the board and run `c/scripts/deploy.sh` to flash and monitor it.

For source-level API pages, run `./scripts/build_docs.sh --c-api` from the repository root. This requires Doxygen in addition to the Python development dependencies.

See the [C README](https://github.com/bygregonline/esp32-sample1/blob/master/c/README.md) for Wi-Fi setup and simulation details.
