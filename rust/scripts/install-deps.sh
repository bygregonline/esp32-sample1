#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

command -v cargo >/dev/null 2>&1 || {
    echo "Instala Rust/Cargo antes de continuar: https://rustup.rs/" >&2
    exit 1
}

if ! command -v espup >/dev/null 2>&1; then
    cargo install espup --locked
fi
espup install --targets esp32s3 --export-file "$PROJECT_DIR/export-esp.sh"

if ! command -v espflash >/dev/null 2>&1; then
    cargo install espflash --locked
fi

if ! command -v ldproxy >/dev/null 2>&1; then
    cargo install ldproxy --locked
fi

if [ -f "$PROJECT_DIR/export-esp.sh" ]; then
    . "$PROJECT_DIR/export-esp.sh"
fi
. "$PROJECT_DIR/scripts/activate-esp-idf.sh"
cargo fetch --manifest-path "$PROJECT_DIR/Cargo.toml"
echo "Toolchain Xtensa, espflash, ldproxy y crates Rust preparados."
echo "En terminales nuevas, ejecuta: . \"$PROJECT_DIR/export-esp.sh\""
