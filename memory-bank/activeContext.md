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

Pending:

- Pull the latest committed repo state on the VPS.
- Create `.env.production` from `.env.example` on the VPS if missing.
- Run `docker compose --env-file .env.production config` on the VPS.
- Start initial VPS services after production env values are filled.

## Next Step

Commit and push Phase 1, update the VPS repo, create the VPS-local `.env.production` template, and validate Docker Compose on the VPS.
