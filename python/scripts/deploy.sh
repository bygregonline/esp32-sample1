#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$PROJECT_DIR/.." && pwd)
OUTPUT_DIR="$PROJECT_DIR/dist/esp32-monitor-python"
CONNECTION=${ESP32_PORT:-auto}

if [ -x "$REPO_ROOT/.venv/bin/mpremote" ]; then
    MPREMOTE="$REPO_ROOT/.venv/bin/mpremote"
elif command -v mpremote >/dev/null 2>&1; then
    MPREMOTE=$(command -v mpremote)
else
    echo "No se encontró mpremote. Ejecuta primero: ./scripts/install-deps.sh" >&2
    exit 1
fi

"$SCRIPT_DIR/build.sh"
cd "$OUTPUT_DIR"
"$MPREMOTE" connect "$CONNECTION" fs cp config.py gps.py bmp280.py ssd1306.py st7789.py moon_image.py main.py :
"$MPREMOTE" connect "$CONNECTION" reset
