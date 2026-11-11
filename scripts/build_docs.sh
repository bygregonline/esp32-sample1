#!/usr/bin/env bash
# Build the MkDocs site (including Python API pages), optionally adding native API HTML.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_c=0
build_rust=0

usage() {
    cat <<'EOF'
Usage: ./scripts/build_docs.sh [--c-api] [--rust-api] [--all]

Without flags, builds MkDocs and the MicroPython API reference.
--c-api additionally runs Doxygen (install it separately).
--rust-api additionally runs cargo doc with the ESP toolchain.
--all builds all three API references.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --c-api) build_c=1 ;;
        --rust-api) build_rust=1 ;;
        --all) build_c=1; build_rust=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

if (( build_c )) && ! command -v doxygen >/dev/null 2>&1; then
    echo "Doxygen is required for --c-api (for example: brew install doxygen)." >&2
    exit 2
fi
if (( build_rust )) && [[ ! -f "$repo_root/rust/export-esp.sh" ]]; then
    echo "Run rust/scripts/install-deps.sh before --rust-api to create rust/export-esp.sh." >&2
    exit 2
fi

cd "$repo_root"
uv run --locked --group dev mkdocs build --strict

if (( build_c )); then
    doxygen c/Doxyfile
    [[ -f site/api/c/index.html ]] || { echo "Doxygen did not create site/api/c/index.html" >&2; exit 1; }
    echo "C API: site/api/c/index.html"
fi

if (( build_rust )); then
    rust_target_dir="$repo_root/rust/target/docs-build"
    (
        cd "$repo_root/rust"
        # shellcheck source=/dev/null
        source ./export-esp.sh
        cargo doc --locked --no-deps --document-private-items --target-dir "$rust_target_dir"
    )
    rust_doc_dir="$rust_target_dir/xtensa-esp32s3-espidf/doc"
    if [[ ! -d "$rust_doc_dir" ]]; then
        rust_doc_dir="$rust_target_dir/doc"
    fi
    [[ -d "$rust_doc_dir" ]] || { echo "cargo doc output was not found" >&2; exit 1; }
    mkdir -p site/api/rust
    cp -R "$rust_doc_dir/." site/api/rust/
    echo "Rust API: site/api/rust/esp32_monitor_rust/index.html"
fi

echo "MkDocs site: site/index.html"
