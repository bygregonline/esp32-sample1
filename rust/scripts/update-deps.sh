#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

if [ -f "$PROJECT_DIR/export-esp.sh" ]; then
    . "$PROJECT_DIR/export-esp.sh"
elif [ -f "$HOME/export-esp.sh" ]; then
    . "$HOME/export-esp.sh"
fi

command -v cargo >/dev/null 2>&1 || {
    echo "No se encontro cargo. Ejecuta primero ./scripts/install-deps.sh." >&2
    exit 1
}

cd "$PROJECT_DIR"
cargo update --manifest-path "$PROJECT_DIR/Cargo.toml"
cargo fetch --manifest-path "$PROJECT_DIR/Cargo.toml"

echo "Dependencias Rust actualizadas. Revisa Cargo.lock y compila con ./scripts/build.sh."
