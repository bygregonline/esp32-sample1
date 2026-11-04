#!/usr/bin/env python3
"""Show sync status of the four implementation directories."""

import subprocess
from pathlib import Path

IMPL_DIRS = ["c", "python", "rust", "arduino"]
ROOT = Path(__file__).parent.parent


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    print("── Implementation status ────────────────────────")
    for d in IMPL_DIRS:
        path = ROOT / d
        if not path.exists():
            print(f"  {d:<10} NOT FOUND")
            continue

        # Last commit touching this directory
        last = git("log", "--oneline", "-1", "--", d) or "(no commits yet)"
        # Uncommitted changes in this directory
        dirty = git("status", "--short", "--", d)
        dirty_flag = " [DIRTY]" if dirty else ""
        print(f"  {d:<10} {last}{dirty_flag}")

    print("─────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
