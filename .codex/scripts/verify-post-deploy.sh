#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <base-url>" >&2
  echo "Example: $0 http://127.0.0.1:8000" >&2
  exit 2
fi

BASE_URL="${1%/}"

case "$BASE_URL" in
  http://*|https://*)
    ;;
  *)
    echo "Base URL must start with http:// or https://." >&2
    exit 2
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is not available; post-deploy verification is UNKNOWN." >&2
  exit 2
fi

echo "Checking health endpoint: $BASE_URL/health"
curl -fsS "$BASE_URL/health" >/dev/null

echo "Health endpoint passed."
