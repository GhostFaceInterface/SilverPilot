---
name: "streamlit-dashboard"
description: "Codex-local skill bundle for Streamlit dashboard code, smoke testing, Docker packaging, and API boundary checks."
---

# Streamlit Dashboard

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Dashboard code must use FastAPI HTTP boundaries, not direct DB access.
- Secure agent endpoints require token headers from environment, never hardcoded tokens.
- Use headless-safe chart rendering in containers.
- Verify import/syntax and dashboard Dockerfile packaging for new local modules.
- Prefer local API smoke checks; production dashboard checks require explicit user approval.

## Commands
```bash
python -m py_compile apps/dashboard/streamlit_app.py
docker compose --profile dashboard config
docker compose --profile dashboard build dashboard
```

## Evidence
- Syntax/import status.
- Docker config/build result or explicit SKIPPED reason.
- Manual/browser smoke status when applicable.
