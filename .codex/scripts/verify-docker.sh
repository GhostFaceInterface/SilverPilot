#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available; Docker verification is UNKNOWN."
  exit 0
fi

echo "Validating default Compose config..."
docker compose config >/dev/null

echo "Validating collector profile Compose config..."
docker compose --profile collector config >/dev/null

echo "Validating dashboard profile Compose config..."
docker compose --profile dashboard config >/dev/null

if [ "${1:-}" = "--build" ]; then
  echo "Building API image..."
  docker compose build api
  echo "Building dashboard image..."
  docker compose --profile dashboard build dashboard
else
  echo "Build skipped. Pass --build to build local images."
fi

echo "Docker Compose verification completed."
