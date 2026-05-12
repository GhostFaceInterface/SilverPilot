# Progress

## Phase 0

Status: complete.

Completed:

- Root directory structure.
- Canonical memory bank files.
- Controlled docs structure.
- Agent spec placeholders.
- API and dashboard folder skeletons.
- Git repository initialized.
- Initial commit pushed to GitHub.
- Full canonical roadmap written to `docs/ROADMAP.md`.
- Phase 0 architecture, data contract, risk policy, decision, tech context, and agent rule docs completed.
- Efficiency baseline added: context loading, DoD, runtime-memory separation, LLM outage rule, and agent budget guard targets.
- VPS bootstrap prerequisite completed: VPS purchased, Docker installed, and SSH alias `silverpilot-vps` tested successfully from Mac.

## Phase 1

Status: complete.

Completed:

- Backend dependency baseline selected in `apps/api/requirements.txt`.
- FastAPI application factory implemented.
- PostgreSQL connection and SQLAlchemy base configured.
- Alembic environment and initial schema migration added.
- Initial entity models added.
- Initial endpoints added: `/health`, `/portfolio`, `/prices/latest`, `/signals/latest`, `/reports/daily/latest`.
- Basic health endpoint test added and passed.
- Local Docker Compose API/PostgreSQL validation passed.
- Development seed command added.
- Phase 1 commit pushed to GitHub.
- VPS repo updated to the latest `main`.
- VPS-local `.env.production` created from `.env.example`.
- VPS Docker Compose config validated with `.env.production`.
- VPS services started with Docker Compose.
- VPS Alembic migration and seed command completed.
- VPS `/health` validated production API/database connectivity.

Validation:

- API and PostgreSQL containers are healthy on the VPS.
- `/health` returns `database: ok`.
- `REAL_MONEY_ENABLED=false` is active.

## Phase 2

Status: complete.

Completed:

- Added paper-trading service for virtual buy/sell/hold/blocked records.
- Added `POST /paper-trades`.
- Added `GET /paper-trades/position`.
- Added portfolio snapshot creation after paper-trade actions.
- Added tests for spread/fee loss, negative-balance protection, and real-money portfolio rejection.
- Local pytest passed.
- Local Docker API rebuild and `/health` validation passed.
- Phase 2 commit pushed to GitHub.
- VPS repo pulled the Phase 2 commit.
- VPS API container rebuilt successfully.
- VPS `/health` validated production API/database connectivity after rebuild.
- VPS `hold` paper-trade smoke test passed.

Validation:

- Same-market buy/sell loses after spread and fees in tests.
- Paper cash balance cannot go negative.
- Real-money portfolios are rejected.
- Paper trades are audit logged in `paper_trades`.

## Phase 3

Status: in progress.

Completed:

- Added `collector_runs`.
- Added raw collector tables for bank prices, global prices, FX rates, news, and events.
- Added `0002_collector_foundation` Alembic migration.
- Added manual bank/global price ingestion service.
- Added `POST /collectors/manual-price`.
- Added `GET /collectors/runs/latest`.
- Added tests for raw/normalized price writes, duplicate detection, and inverted spread rejection.
- Local pytest passed.
- Local Alembic migration, API rebuild, `/health`, collector run, and latest price validations passed.
- Phase 3 foundation commit pushed to GitHub.
- VPS repo pulled the Phase 3 foundation commit.
- VPS API container rebuilt successfully.
- VPS Alembic migration reached `0002_collector_foundation`.
- VPS manual price ingestion smoke test passed.
- VPS duplicate guard returned no new price snapshot for repeated observation.
- Added collector runner module.
- Added opt-in Docker Compose `collector` profile.
- Added `GET /collectors/health`.
- Added collector health tests.
- Local runner one-shot and collector health validation passed.
- Scheduled collector support commit pushed to GitHub.
- VPS repo pulled the scheduled collector support commit.
- VPS API container rebuilt successfully.
- VPS runner one-shot validation passed.
- VPS collector health endpoint returned `ok`.

Next milestone:

- Select and implement the first real configurable price source collector.
