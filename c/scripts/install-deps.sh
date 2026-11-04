#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

. "$SCRIPT_DIR/activate-esp-idf.sh"

cd "$PROJECT_DIR"
"$ESP_IDF_PYTHON" "$IDF_PATH/tools/idf.py" reconfigure
echo "ESP-IDF configuró las dependencias del proyecto."
