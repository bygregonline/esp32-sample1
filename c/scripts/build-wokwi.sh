#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
BUILD_DIR="$PROJECT_DIR/build-wokwi"
SDKCONFIG_FILE="$BUILD_DIR/sdkconfig"
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.wokwi.defaults"

. "$SCRIPT_DIR/activate-esp-idf.sh"

cd "$PROJECT_DIR"
if [ ! -f "$SDKCONFIG_FILE" ]; then
    "$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" -B "$BUILD_DIR" \
        -D "SDKCONFIG=$SDKCONFIG_FILE" \
        -D "SDKCONFIG_DEFAULTS=$SDKCONFIG_DEFAULTS" set-target esp32
fi

"$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" -B "$BUILD_DIR" \
    -D "SDKCONFIG=$SDKCONFIG_FILE" \
    -D "SDKCONFIG_DEFAULTS=$SDKCONFIG_DEFAULTS" build

echo "Firmware Wokwi listo: $BUILD_DIR/flasher_args.json"
