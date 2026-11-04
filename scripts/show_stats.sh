#!/usr/bin/env bash
# Show a brief summary of the repo at commit time.
set -euo pipefail

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMITS=$(git rev-list --count HEAD 2>/dev/null || echo "?")
FILES=$(git ls-files | wc -l | tr -d ' ')
CHANGED=$(git diff --cached --name-only | wc -l | tr -d ' ')

echo "──────────────────────────────────────────"
echo "  Branch  : $BRANCH"
echo "  Commits : $COMMITS"
echo "  Tracked : $FILES files"
echo "  Staged  : $CHANGED file(s) in this commit"
echo "──────────────────────────────────────────"
