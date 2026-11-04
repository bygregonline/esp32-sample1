#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

"$SCRIPT_DIR/build.sh"
cd "$PROJECT_DIR"
if [ -n "${ESP32_PORT:-}" ]; then
    idf.py -p "$ESP32_PORT" flash monitor
else
    idf.py flash monitor
fi
