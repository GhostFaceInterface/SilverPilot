# Worklog

## 2026-05-12

Phase 0 started.

- Created root project skeleton.
- Created memory bank and controlled docs structure.
- Created short agent spec placeholders.
- Created API, dashboard, scripts, data, and notebooks folders.
- Confirmed no real-money or bank automation implementation exists.

Roadmap correction.

- Expanded `docs/ROADMAP.md` from phase index into the canonical detailed roadmap.
- Updated memory context to show Phase 0 skeleton is complete and Phase 1 has not started.

Phase 0 documentation audit.

- Expanded architecture, data contracts, risk policy, decisions, tech context, agent rules, and agent specs.
- Updated README, AGENTS, and `.env.example` with missing operational guardrails.

Efficiency baseline.

- Added context loading protocol, task definition of done, markdown creation rule, runtime-memory separation, LLM outage requirement, buy-and-hold benchmark rule, and initial agent budget targets.

## 2026-05-13

VPS SSH bootstrap verified.

- VPS has been purchased and prepared for SilverPilot deployment work.
- Docker is installed on the VPS.
- Local SSH alias `silverpilot-vps` is configured on the developer Mac.
- `ssh silverpilot-vps` successfully connects to the server.
- No secrets were added to the repository.
- Next: verify `/opt/silverpilot`, clone/create project skeleton, prepare `.env.production`, and validate Docker Compose.

Phase 1 backend core implemented locally.

- Added FastAPI application factory and initial endpoints.
- Added PostgreSQL config, SQLAlchemy models, and Alembic initial migration.
- Added API Dockerfile, Compose API service, and private PostgreSQL networking.
- Added basic `/health` test and development seed command.
- Validated: pytest passed, Compose config passed, migration ran, API container healthy, `/health` returned database ok.
- Next: commit/push, pull on VPS, create VPS-local `.env.production` from `.env.example`, and validate VPS Compose config.

Phase 1 pushed and VPS config bootstrap verified.

- Committed and pushed Phase 1 backend core.
- Updated the VPS repo under `/opt/silverpilot/SilverPilot`.
- Created VPS-local `.env.production` from `.env.example` without printing file contents.
- Validated VPS Compose config with `docker compose --env-file .env.production config`.
- Did not start VPS services because production values still need manual editing.
- Next: user fills `.env.production`, then run VPS services, migration, seed, and `/health` validation.

Phase 1 VPS runtime verified.

- User filled VPS-local `.env.production` without adding secrets to git.
- VPS services started with `docker compose --env-file .env.production up -d --build`.
- VPS Alembic migration and seed command completed successfully.
- VPS `/health` returned production `database: ok` and `real_money_enabled: false`.
- Observed an editor swap file from env editing; added gitignore coverage for swap files.
- Next: begin Phase 2 paper-trading engine.

Phase 2 paper-trading core implemented locally.

- Added deterministic paper-trading service for `paper_buy`, `paper_sell`, `hold`, and `blocked`.
- Added `/paper-trades` and `/paper-trades/position` API endpoints.
- Paper trades update virtual cash and create portfolio snapshots.
- Tests passed for spread/fee loss, negative-balance protection, and real-money portfolio rejection.
- Local API image rebuilt and `/health` validation passed.
- Next: deploy Phase 2 to the VPS and run a paper-trade smoke test.

Phase 2 deployed and verified on VPS.

- Pushed Phase 2 paper-trading commit to GitHub.
- Pulled latest `main` on the VPS and rebuilt the API container.
- VPS `/health` returned production `database: ok`.
- VPS `POST /paper-trades` smoke test created a `hold` audit record.
- VPS `/paper-trades/position` showed 600 USD cash and 0 XAG.
- Next: begin Phase 3 data collector foundations.

Phase 3 collector foundation implemented locally.

- Added collector run tracking and raw collector tables.
- Added manual bank/global price ingestion into raw tables plus normalized `price_snapshots`.
- Added latest collector run endpoint.
- Added duplicate detection for price observations.
- Tests passed for ingestion, duplicate handling, and spread validation.
- Local migration, API rebuild, `/health`, collector run, and latest price checks passed.
- Next: deploy Phase 3 migration and smoke test manual ingestion on VPS.

Phase 3 collector foundation deployed on VPS.

- Pushed Phase 3 foundation commit to GitHub and pulled it on the VPS.
- Rebuilt the VPS API container.
- Ran Alembic migration to `0002_collector_foundation`.
- VPS manual price ingestion created raw and normalized price records.
- VPS duplicate guard returned `records_inserted: 0` and `duplicates: 1`.
- Next: add scheduled collector execution and collector health visibility.

Phase 3 scheduled collector support implemented locally.

- Added `python -m app.collectors.runner` for one-shot or looped collector execution.
- Added opt-in Docker Compose `collector` profile.
- Added `/collectors/health` with stale-run detection.
- Added tests for empty, healthy, and invalid collector health checks.
- Local runner one-shot wrote a collector run and price snapshot.
- Next: deploy runner and collector health visibility to VPS.

Phase 3 scheduled collector support deployed on VPS.

- Pushed scheduled collector support commit to GitHub and pulled it on VPS.
- Rebuilt VPS API container.
- VPS `/collectors/health` returned `ok`.
- VPS one-shot collector runner wrote a successful collector run and price snapshot.
- Collector profile remains opt-in, not continuously running by default.
- Next: select and implement the first real configurable price source collector.

Phase 3 free-source data policy updated.

- Set MVP source policy to free/public-source first; paid market-data APIs remain disabled.
- Added public collector rules for no login/bypass, polite polling, raw payload hashes, parser versioning, and visible failures.
- Classified primary MVP candidates as Kuveyt Türk public page POC, TCMB daily XML, Stooq XAG/USD quote, Fed RSS, BLS, and FRED.
- Kept Yahoo Finance and Investing as diagnostic/fallback only.
- Added no-cost API-key setup to the Phase 3.1 todo list for BLS and FRED; key values must remain outside markdown and git.

Phase 3.1 public-source collectors implemented locally.

- Added collector audit fields for `fetched_at`, `raw_payload_hash`, and `parser_version`.
- Added Kuveyt public silver page POC, Stooq XAG/USD CSV, and TCMB USD/TRY XML collectors.
- Added runner job selection and API run endpoints for the new collectors.
- Added optional no-cost `BLS_API_KEY` and `FRED_API_KEY` placeholders without enabling paid APIs.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `docker compose config`, and `compileall`.
- Next: commit/push, pull on VPS, run migration `0003`, then smoke test TCMB/Stooq/Kuveyt collector runs.

CI/CD baseline added locally.

- Added GitHub Actions workflow for backend tests, Docker Compose validation, and API image build on push and pull request.
- Added manual VPS smoke/deploy workflow path guarded by repository secrets and `workflow_dispatch`.
- VPS smoke covers git pull, Compose config, rebuild, Alembic migration, `/health`, TCMB collector, Stooq collector, optional Kuveyt collector, and collector health.
- Documented required VPS secrets without storing secret values.
- Next: push workflow, configure GitHub repository secrets, then run the manual VPS smoke workflow.
