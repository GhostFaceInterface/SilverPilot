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

Status: in progress.

Completed:

- Added paper-trading service for virtual buy/sell/hold/blocked records.
- Added `POST /paper-trades`.
- Added `GET /paper-trades/position`.
- Added portfolio snapshot creation after paper-trade actions.
- Added tests for spread/fee loss, negative-balance protection, and real-money portfolio rejection.
- Local pytest passed.
- Local Docker API rebuild and `/health` validation passed.

Next milestone:

- Commit/push Phase 2 and validate it on the VPS.
