#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

if [ ! -d "apps/api/tests" ]; then
  echo "apps/api/tests not found; no pytest suite detected."
  exit 0
fi

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" -c 'import ast, pathlib; ast.parse(pathlib.Path(".codex/scripts/readonly-db-check.py").read_text())'

if "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pytest apps/api/tests
else
  echo "pytest is not available for $PYTHON_BIN" >&2
  exit 1
fi
