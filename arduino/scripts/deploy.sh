#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
SKETCH_DIR="$PROJECT_DIR/esp32_monitor"
BUILD_DIR="$PROJECT_DIR/build"
OUTPUT_DIR="$PROJECT_DIR/dist"
ARDUINO_FQBN=${ARDUINO_FQBN:-esp32:esp32:esp32}

command -v arduino-cli >/dev/null 2>&1 || {
    echo "No se encontró arduino-cli. Instálalo y ejecuta ./scripts/install-deps.sh." >&2
    exit 1
}

if [ -z "${ESP32_PORT:-}" ]; then
    echo "Define ESP32_PORT con el puerto serial de la placa, por ejemplo:" >&2
    echo "ESP32_PORT=/dev/cu.usbserial-0001 ./scripts/deploy.sh" >&2
    exit 1
fi

mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
arduino-cli compile \
    --fqbn "$ARDUINO_FQBN" \
    --port "$ESP32_PORT" \
    --upload \
    --build-path "$BUILD_DIR" \
    --output-dir "$OUTPUT_DIR" \
    "$SKETCH_DIR"
