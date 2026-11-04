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

mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
arduino-cli compile \
    --fqbn "$ARDUINO_FQBN" \
    --build-path "$BUILD_DIR" \
    --output-dir "$OUTPUT_DIR" \
    "$SKETCH_DIR"

echo "Compilación Arduino lista. Binarios en: $OUTPUT_DIR"
