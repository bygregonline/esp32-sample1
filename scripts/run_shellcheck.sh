#!/usr/bin/env bash
# Run shellcheck on all shell scripts under specified root directories.
# Usage: run_shellcheck.sh --roots "dir1 dir2 ..."
set -euo pipefail

ROOTS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --roots) ROOTS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if ! command -v shellcheck &>/dev/null; then
  echo "shellcheck not found — skipping (install with: brew install shellcheck)" >&2
  exit 0
fi

FAILED=0
for root in $ROOTS; do
  while IFS= read -r -d '' script; do
    echo "  → $script"
    if ! shellcheck -x -S warning "$script"; then
      FAILED=1
    fi
  done < <(find "$root" -name "*.sh" -print0 2>/dev/null)
done

exit "$FAILED"
