#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

echo "== Branch =="
git branch --show-current
echo

echo "== Status =="
git status --short
echo

echo "== Diff summary =="
git diff --stat || true
echo

echo "== Staged diff summary =="
git diff --cached --stat || true
echo

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "Working tree is clean."
else
  echo "Working tree has changes."
fi

echo
echo "== Suspicious changed files =="
suspicious_found=0

changed_paths=()

add_path() {
  local path="$1"
  [ -n "$path" ] || return 0
  changed_paths+=("$path")
}

while IFS= read -r -d '' path; do
  add_path "$path"
done < <(git diff --name-only -z --diff-filter=ACMRT)

while IFS= read -r -d '' path; do
  add_path "$path"
done < <(git diff --cached --name-only -z --diff-filter=ACMRT)

while IFS= read -r -d '' path; do
  add_path "$path"
done < <(git ls-files --others --exclude-standard -z)

scan_secret_patterns() {
  local path="$1"

  if ! [ -f "$path" ]; then
    return 0
  fi

  if ! grep -Iq . "$path" 2>/dev/null; then
    return 0
  fi

  if grep -Eq -- '-----BEGIN (RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----' "$path"; then
    echo "SECRET_PATTERN: $path (private key block)"
    return 1
  fi

  if grep -Eq -- 'sk-[A-Za-z0-9_-]{20,}' "$path"; then
    echo "SECRET_PATTERN: $path (OpenAI-style API key)"
    return 1
  fi

  if grep -Eq -- '(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})' "$path"; then
    echo "SECRET_PATTERN: $path (GitHub token)"
    return 1
  fi

  if grep -Eq -- 'sb_(publishable|secret)_[A-Za-z0-9_-]{20,}' "$path"; then
    echo "SECRET_PATTERN: $path (Supabase key)"
    return 1
  fi

  if grep -Eiq -- '(^|[^A-Za-z0-9_])(api[_-]?key|access[_-]?token|auth[_-]?token|secret|jwt[_-]?secret|password)[[:space:]]*[:=][[:space:]]*["'\'']?[^"'\''[:space:]{}$]{12,}' "$path"; then
    echo "SECRET_PATTERN: $path (secret-like assignment)"
    return 1
  fi

  if grep -Eiq -- '(postgres(ql)?|mysql|mariadb|redis)://[^[:space:]"'\'']+:[^[:space:]"'\'']+@' "$path"; then
    if ! grep -Eiq -- '(change_me|example|password|localhost|127\.0\.0\.1)' "$path"; then
      echo "SECRET_PATTERN: $path (database URL with credentials)"
      return 1
    fi
  fi

  return 0
}

if [ "${#changed_paths[@]}" -eq 0 ]; then
  echo "No changed or untracked paths to scan."
else
  for path in "${changed_paths[@]}"; do
    case "$path" in
      *.env|*.env.*|*.pem|*.key|*.p12|*.pfx|*.crt|*.sql|*.sqlite|*.db|*.dump|*.tar|*.tgz|*.gz|*.zip|*.7z|*.rar|*.pkl|*.joblib|*.onnx|*.pt|*.pth|*.h5|*__pycache__*|*.pyc)
        echo "SUSPICIOUS: $path"
        suspicious_found=1
        ;;
    esac
    if [ -f "$path" ]; then
      size_bytes="$(stat -f%z "$path" 2>/dev/null || stat -c%s "$path" 2>/dev/null || echo 0)"
      if [ "$size_bytes" -gt 52428800 ]; then
        echo "LARGE FILE: $path (${size_bytes} bytes)"
        suspicious_found=1
      fi
    fi

    if ! scan_secret_patterns "$path"; then
      suspicious_found=1
    fi
  done
fi

if [ "$suspicious_found" -ne 0 ]; then
  echo "Suspicious files detected. Review before commit."
  exit 2
fi

echo "No suspicious changed files detected."
