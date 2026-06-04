---
name: "alembic-migrations"
description: "Codex-local skill bundle for SQLAlchemy and Alembic migration safety in SilverPilot."
---

# Alembic Migrations

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Use When
- SQLAlchemy models, Alembic revisions, indexes, constraints, or database schema behavior changes.
- Migration risk must be reviewed before commit, push, or deploy.

## Rules
- Inspect migration files before running them.
- Do not mutate staging or production databases without explicit user approval.
- Every upgrade needs a safe downgrade or a documented irreversible-risk note.
- Validate SQLite test compatibility and PostgreSQL production assumptions separately.
- Review data-loss, lock, index, backfill, and timezone risks.

## Safe Evidence
- Migration file path and revision id.
- Static review of upgrade/downgrade operations.
- Local/test database migration result when available.
- Data-loss risk classification: LOW / MEDIUM / HIGH / UNKNOWN.

## Commands
```bash
cd apps/api
alembic history
alembic current
alembic upgrade head
```

Only run migration commands against local/test databases unless the user explicitly approves a target.
