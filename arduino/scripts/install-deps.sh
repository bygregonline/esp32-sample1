#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
BOARD_INDEX_URL=${ESP32_BOARD_INDEX_URL:-https://espressif.github.io/arduino-esp32/package_esp32_index.json}

command -v arduino-cli >/dev/null 2>&1 || {
    echo "No se encontró arduino-cli. En macOS puedes instalarlo con: brew install arduino-cli" >&2
    exit 1
}

arduino-cli core update-index --additional-urls "$BOARD_INDEX_URL"
arduino-cli core install esp32:esp32 --additional-urls "$BOARD_INDEX_URL"
arduino-cli lib install \
    "GFX Library for Arduino" \
    "Adafruit SSD1306" \
    "Adafruit GFX Library" \
    "DHT sensor library" \
    "Adafruit Unified Sensor" \
    "TinyGPSPlus"

echo "Core ESP32 y bibliotecas del sketch listos. Proyecto: $PROJECT_DIR"
