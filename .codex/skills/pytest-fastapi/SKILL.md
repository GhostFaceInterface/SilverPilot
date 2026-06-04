---
name: "pytest-fastapi"
description: "Codex-local skill bundle for FastAPI pytest execution, targeted regression tests, and mock integrity."
---

# Pytest FastAPI

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Prefer targeted pytest first, then broaden when risk justifies it.
- Run from a context where `apps/api` imports resolve.
- Keep tests isolated from production/staging databases.
- Patch the namespace used by runtime code.
- Treat live network calls as failures unless explicitly approved.

## Commands
```bash
bash .codex/scripts/verify-tests.sh
cd apps/api
python -m pytest tests
```

## Evidence
- Command, exit status, and test count.
- Skips/warnings that matter.
- What was not tested.
