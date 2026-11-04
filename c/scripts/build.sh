#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

. "$SCRIPT_DIR/activate-esp-idf.sh"

cd "$PROJECT_DIR"
if [ ! -f sdkconfig ]; then
    "$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" set-target esp32
fi
"$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" build
echo "Firmware listo: $PROJECT_DIR/build/esp32_monitor_c.bin"
