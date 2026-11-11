#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

"$SCRIPT_DIR/build.sh"
cd "$PROJECT_DIR"
if [ -n "${ESP32_PORT:-}" ]; then
    espflash flash --chip esp32s3 --port "$ESP32_PORT" --monitor \
        target/xtensa-esp32s3-espidf/release/esp32-monitor-rust
else
    espflash flash --chip esp32s3 --monitor \
        target/xtensa-esp32s3-espidf/release/esp32-monitor-rust
fi
