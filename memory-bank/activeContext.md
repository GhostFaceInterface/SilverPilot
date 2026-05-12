# Active Context

## Current Phase

Phase 2: paper-trading engine complete.

## Current State

- Project root exists.
- Canonical memory bank structure exists.
- Agent-specific short spec files exist.
- FastAPI application factory exists.
- PostgreSQL connection and Alembic migration setup exist.
- Initial SQLAlchemy models exist for Phase 1 entities.
- Initial API endpoints exist: `/health`, `/portfolio`, `/prices/latest`, `/signals/latest`, `/reports/daily/latest`.
- Paper-trading service exists for `paper_buy`, `paper_sell`, `hold`, and `blocked` records.
- Paper-trading API endpoint exists at `POST /paper-trades`.
- Paper position endpoint exists at `GET /paper-trades/position`.
- Paper trades update virtual cash balance and create portfolio snapshots.
- Local tests validate spread/fee loss, negative-balance protection, and real-money portfolio rejection.
- VPS API was rebuilt with Phase 2 code.
- VPS paper-trade smoke test passed with a `hold` audit record and unchanged 600 USD paper balance.
- Local Docker Compose API/PostgreSQL validation passed.
- VPS repo was updated to the latest `main` commit.
- VPS-local `.env.production` was created from `.env.example` without printing secrets.
- VPS Docker Compose config validation passed with `.env.production`.
- VPS services started successfully with Docker Compose.
- VPS Alembic migration and seed command completed successfully.
- VPS `/health` returns production `database: ok` and `real_money_enabled: false`.
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

- Keep VPS-local `.env.production` secrets out of git and markdown.
- Ignore editor swap files created while editing production env files.

## Next Step

Start Phase 3: implement price/news collector foundations without adding LLM or ML behavior.
