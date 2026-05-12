# Active Context

## Current Phase

Phase 1: backend core.

## Current State

- Project root exists.
- Canonical memory bank structure exists.
- Agent-specific short spec files exist.
- FastAPI application factory exists.
- PostgreSQL connection and Alembic migration setup exist.
- Initial SQLAlchemy models exist for Phase 1 entities.
- Initial API endpoints exist: `/health`, `/portfolio`, `/prices/latest`, `/signals/latest`, `/reports/daily/latest`.
- Local Docker Compose API/PostgreSQL validation passed.
- VPS repo was updated to the latest `main` commit.
- VPS-local `.env.production` was created from `.env.example` without printing secrets.
- VPS Docker Compose config validation passed with `.env.production`.
- Full canonical roadmap exists in `docs/ROADMAP.md`.
- Architecture, data contracts, risk policy, decisions, tech context, and agent rules have Phase 0 detail.
- Efficiency rules now distinguish development memory from runtime database memory.
- No real-money integration exists.
- No bank automation exists.

## Current Infrastructure Status

- VPS acquired.
- Docker installed on VPS.
- SSH alias `silverpilot-vps` is configured on the developer Mac.
- `ssh silverpilot-vps` successfully connects to the server.
- Agents may use this SSH alias for VPS-related tasks when explicitly asked.
- Current VPS project path: `/opt/silverpilot/SilverPilot`.

Pending:

- User must fill real production values in VPS-local `.env.production`.
- Start initial VPS services after production env values are filled.
- Run Alembic migration and seed command on the VPS after services start.

## Next Step

Fill `.env.production` on the VPS, then start VPS services and run migration/seed validation.
