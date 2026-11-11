#!/bin/sh
# Source the repository's shared local ESP-IDF activator for Rust builds.

if [ -z "${PROJECT_DIR:-}" ] || [ -z "${REPO_ROOT:-}" ]; then
    echo "Define PROJECT_DIR and REPO_ROOT before sourcing this script." >&2
    return 1
fi

. "$REPO_ROOT/c/scripts/activate-esp-idf.sh"

# Ensure the local repository's idf.py is the one discovered from PATH; EIM's
# shim can otherwise look like a different ESP-IDF tree to esp-idf-sys.
PATH="$IDF_PATH/tools:$PATH"
export PATH

# ESP-IDF 5.4 uses Python 3.12. Give build scripts a `python3` command that
# resolves to the installed 3.12 interpreter even if the shell's default is newer.
if command -v python3.12 >/dev/null 2>&1; then
    _rust_python_shim_dir="$PROJECT_DIR/.build-tools/python312"
    mkdir -p "$_rust_python_shim_dir"
    ln -sf "$(command -v python3.12)" "$_rust_python_shim_dir/python3"
    PATH="$_rust_python_shim_dir:$PATH"
    export PATH
fi

# Tell esp-idf-sys to use the environment activated by the shared local helper.
ESP_IDF_TOOLS_INSTALL_DIR=fromenv
export ESP_IDF_TOOLS_INSTALL_DIR

unset _rust_python_shim_dir
