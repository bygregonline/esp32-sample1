#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$PROJECT_DIR/.." && pwd)

command -v uv >/dev/null 2>&1 || {
    echo "No se encontró uv. Instálalo con Homebrew: brew install uv" >&2
    exit 1
}

cd "$REPO_ROOT"
uv sync --python 3.12
echo "Entorno Python 3.12 y mpremote listos en: $REPO_ROOT/.venv"
