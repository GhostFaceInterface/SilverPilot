#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is not available; CI status is UNKNOWN."
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is installed but not authenticated for this repository; CI status is UNKNOWN."
  exit 0
fi

echo "Recent GitHub Actions runs:"
gh run list --limit 10
