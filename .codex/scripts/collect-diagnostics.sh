#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

echo "== SilverPilot safe diagnostics =="
echo "Repository: $ROOT_DIR"
echo

echo "== Python =="
if command -v python3 >/dev/null 2>&1; then
  python3 --version
elif command -v python >/dev/null 2>&1; then
  python --version
else
  echo "python: not found"
fi
echo

echo "== Package manager hints =="
if [ -f "apps/api/requirements.txt" ]; then
  echo "apps/api/requirements.txt: present"
fi
if [ -f "apps/dashboard/requirements.txt" ]; then
  echo "apps/dashboard/requirements.txt: present"
fi
if [ -x ".venv/bin/python" ]; then
  echo ".venv: present"
fi
echo

echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
  docker --version
  docker compose version 2>/dev/null || echo "docker compose: unavailable"
else
  echo "docker: not found"
fi
echo

echo "== Git =="
git branch --show-current 2>/dev/null || true
git status --short
echo

echo "== Codex framework tree =="
find .codex -maxdepth 2 -type f | sort
echo

echo "== Project verification entrypoints =="
find .github/workflows apps/api/tests .codex/scripts -maxdepth 2 -type f 2>/dev/null | sort
