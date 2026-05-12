# Active Context

## Current Phase

Phase 3: data collector foundations in progress.

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
- Collector run tracking models and migration exist locally.
- Raw collector tables exist for bank prices, global prices, FX rates, news, and events.
- Manual price ingestion endpoint exists at `POST /collectors/manual-price`.
- Latest collector run endpoint exists at `GET /collectors/runs/latest`.
- Manual price ingestion writes append-only raw price data and normalized `price_snapshots`.
- VPS Alembic migration is at `0002_collector_foundation`.
- VPS manual price ingestion smoke test passed.
- VPS duplicate guard returned `records_inserted: 0` and `duplicates: 1` for repeated observation.
- Collector runner exists at `python -m app.collectors.runner`.
- Docker Compose has an opt-in `collector` profile; it is not started by default.
- Collector health endpoint exists at `GET /collectors/health`.
- Local runner one-shot and collector health validation passed.
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

- Deploy scheduled collector runner and health visibility to VPS.
- Keep VPS-local `.env.production` secrets out of git and markdown.
- Ignore editor swap files created while editing production env files.

## Next Step

Commit/push scheduled collector runner, pull on VPS, rebuild API, and validate collector health.
