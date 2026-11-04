#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

# Cargar entorno de Espressif (espup) si existe
if [ -f "$PROJECT_DIR/export-esp.sh" ]; then
    . "$PROJECT_DIR/export-esp.sh"
elif [ -f "$HOME/export-esp.sh" ]; then
    . "$HOME/export-esp.sh"
fi

command -v cargo >/dev/null 2>&1 || {
    echo "No se encontro cargo. Instala el toolchain Xtensa con espup." >&2
    exit 1
}
command -v espflash >/dev/null 2>&1 || {
    echo "No se encontro espflash. Instala con: cargo install espflash --locked" >&2
    exit 1
}
command -v ldproxy >/dev/null 2>&1 || {
    echo "No se encontro ldproxy. Ejecuta: ./scripts/install-deps.sh" >&2
    exit 1
}

cd "$PROJECT_DIR"

# Target std para ESP32 (ESP-IDF)
cargo build --release

espflash save-image --chip esp32 \
    target/xtensa-esp32-espidf/release/esp32-monitor-rust firmware.bin

echo "Firmware listo: $PROJECT_DIR/firmware.bin"
