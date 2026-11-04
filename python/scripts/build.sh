#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR="$PROJECT_DIR/dist/esp32-monitor-python"

command -v python3 >/dev/null 2>&1 || {
    echo "Se requiere python3 en la computadora de desarrollo." >&2
    exit 1
}

mkdir -p "$OUTPUT_DIR"
cp "$PROJECT_DIR/config.py" "$PROJECT_DIR/gps.py" \
   "$PROJECT_DIR/ssd1306.py" "$PROJECT_DIR/st7789.py" \
   "$PROJECT_DIR/main.py" "$OUTPUT_DIR/"
cat > "$OUTPUT_DIR/MANIFEST.txt" <<'EOF'
Monitor de telemetría ESP32 — MicroPython
Copiar todos los archivos .py al directorio raíz del sistema de archivos de la placa.
EOF

echo "Paquete MicroPython preparado en: $OUTPUT_DIR"
