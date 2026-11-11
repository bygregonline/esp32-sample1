#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$PROJECT_DIR/.." && pwd)
[ ! -f "$REPO_ROOT/.env" ] || . "$REPO_ROOT/.env"
: "${MONITOR_TZ:=CST6}"
export MONITOR_TZ

. "$SCRIPT_DIR/activate-esp-idf.sh"

cd "$PROJECT_DIR"
if [ ! -f sdkconfig ] || ! grep -q '^CONFIG_IDF_TARGET="esp32s3"$' sdkconfig; then
    "$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" set-target esp32s3
fi
"$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" build
echo "Firmware listo: $PROJECT_DIR/build/esp32_monitor_c.bin"
