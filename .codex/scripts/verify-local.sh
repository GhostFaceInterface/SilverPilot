#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

echo "== Level 0: static sanity =="
bash .codex/scripts/verify-git-clean.sh

echo
echo "== Level 1/2: pytest =="
bash .codex/scripts/verify-tests.sh

echo
echo "== Level 3: Docker Compose config =="
bash .codex/scripts/verify-docker.sh

echo
echo "Local verification completed."
