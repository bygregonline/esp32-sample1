#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$PROJECT_DIR/.." && pwd)
[ ! -f "$REPO_ROOT/.env" ] || . "$REPO_ROOT/.env"
: "${MONITOR_TZ:=CST6}"
export MONITOR_TZ
export ESP_IDF_SDKCONFIG_DEFAULTS="$PROJECT_DIR/sdkconfig.defaults"

# Cargar entorno de Espressif (espup) si existe
if [ -f "$PROJECT_DIR/export-esp.sh" ]; then
    . "$PROJECT_DIR/export-esp.sh"
elif [ -f "$HOME/export-esp.sh" ]; then
    . "$HOME/export-esp.sh"
fi

# Usar la instalación local de ESP-IDF, igual que la versión C.
. "$SCRIPT_DIR/activate-esp-idf.sh"

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

espflash save-image --chip esp32s3 \
    target/xtensa-esp32s3-espidf/release/esp32-monitor-rust firmware.bin

echo "Firmware listo: $PROJECT_DIR/firmware.bin"
