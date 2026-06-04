---
name: "fastapi-sqlalchemy"
description: "Codex-local skill bundle for FastAPI, SQLAlchemy, service-layer, and database-access conventions."
---

# FastAPI SQLAlchemy

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Models live under `apps/api/app/models/`.
- Schemas live under `apps/api/app/schemas/`.
- Database query behavior belongs in services or model helpers, not ad hoc router code.
- Avoid N+1 patterns; use eager loading or set-based queries.
- Mutations need transaction handling and rollback paths.
- Do not mutate production/staging databases from Codex without explicit user approval.

## Evidence
- Affected route/service/model path.
- Query path and transaction boundary.
- Tests covering route/service/database interaction.
