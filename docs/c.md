# C / ESP-IDF

The C implementation is the reference firmware. It uses ESP-IDF 5.x, FreeRTOS, and the ESP HTTP server. Its GPIO map lives in `c/main/config.h`.

```sh
cd c
./scripts/install-deps.sh
./scripts/build.sh
```

The build creates `c/build/esp32_monitor_c.bin`. Connect the board and run `c/scripts/deploy.sh` to flash and monitor it.

For source-level API pages, run `./scripts/build_docs.sh --c-api` from the repository root. This requires Doxygen in addition to the Python development dependencies.

See the [C README](https://github.com/bygregonline/esp32-sample1/blob/master/c/README.md) for Wi-Fi setup and simulation details.
