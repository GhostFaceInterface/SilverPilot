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

FRED-first macro strategy documented.

- Recorded that `FRED_API_KEY` exists locally without writing or reading its value.
- Updated the MVP data strategy: FRED is the no-cost macro-series gateway; direct BLS is deferred.
- Added initial FRED series list for CPI, PPI, unemployment, fed funds, 10-year yield, and broad dollar index.
- Classified Türkiye data as execution/risk context for TRY, bank spread, local macro, and tax/rule validation.
- Added advanced memory-layer research to backlog only; no implementation or new markdown files were created.

Lightweight runtime memory architecture added.

- Added Phase 6.5 PostgreSQL-first runtime memory to the roadmap.
- Chose compact operational memory over Zep/Graphiti and external graph-memory services for now.
- Documented memory contracts, exclusions, and risk-policy boundaries.
- Fed RSS/FRED collector next-step order remains unchanged.
- No code implementation or new markdown files were created.

Fed RSS collector implemented locally.

- Added `fed_rss` collector using the official Federal Reserve monetary policy RSS feed.
- Added append-only `raw_news` ingestion with duplicate URL handling.
- Added runner job `--job fed-rss` and env placeholders for `FED_RSS_ENABLED` and `FED_RSS_URL`.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `docker compose config --quiet`, and `compileall`.
- VPS validation passed: Compose config/build, Alembic upgrade, `/health`, and `fed-rss` runner.
- First Fed RSS runner attempt hit transient network unreachable; retry succeeded and inserted 15 items.
- Next: implement FRED macro collector.

FRED macro collector implemented locally.

- Added `fred_macro` collector using FRED `series/observations` JSON responses.
- Added append-only `raw_events` ingestion for `fred_macro_observation` records with duplicate handling.
- Added runner job `--job fred-macro` and env placeholders for FRED base URL and series IDs.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `docker compose config --quiet`, and `compileall`.
- No secret values were read or written.
- Next: commit/push, run CI, pull on VPS, and smoke test `fred-macro`.

FRED macro collector deployed on VPS.

- Pushed FRED macro collector and pulled commit `b0cefb6` on the VPS.
- VPS Compose config/build, Alembic upgrade, and `/health` passed.
- VPS `fred-macro` runner succeeded and inserted 6 configured FRED observations.
- Collector health now includes successful `fred_macro`; overall health remains degraded because Kuveyt public parser fails safely and old manual smoke runs are stale.
- Added Compose env passthrough for Fed RSS and FRED source settings after smoke validation.
- Next: sustained collector validation and execution-critical bank silver source resolution.

Phase 3.4 bank silver source resolution started.

- Confirmed Kuveyt Türk official page exposes GMS data through public browser-loaded finance portal JSON, not static HTML.
- Updated Kuveyt collector to parse public GMS buy/sell data without login, bypass, private endpoint use, or fake fallback.
- Updated collector health states for execution-critical bank price: `healthy`, `degraded`, `blocked`, and `stale`.
- Documented manual bank-price input as degraded simulation fallback only.
- Local tests passed; next: VPS smoke test for `kuveyt-silver`.

Phase 3.4 Kuveyt bank silver smoke passed on VPS.

- Pushed commit `1f79c70` and pulled it on the VPS.
- VPS Compose config/build and Alembic upgrade passed.
- VPS `kuveyt-silver` runner succeeded and inserted a fresh `kuveyt-public-silver-page` bank price.
- VPS collector health reports execution-critical bank price as fresh; overall health remains degraded only because old manual smoke rows are stale.
- Next: sustained collector validation for freshness, duplicate behavior, and missing-data ratio.

Phase 3.4 sustained collector validation support added.

- Added `COLLECTOR_JOBS` comma-separated multi-job runner support while keeping single `COLLECTOR_JOB` compatibility.
- Added `GET /collectors/quality` to summarize recent run count, failures, duplicates, and missing-run ratio.
- Updated CI smoke to require Kuveyt collector success and query collector quality.
- Local validation passed: pytest, Compose config, compileall, and diff check.
- Next: deploy to VPS and run a sustained multi-job collector validation window.

Sustained collector validation started on VPS.

- Deployed commit `3d39450` to VPS.
- Started the collector profile with `COLLECTOR_JOBS=kuveyt-silver,stooq-xag-usd,tcmb-usd-try,fed-rss,fred-macro`.
- Initial collector loop succeeded for all five jobs.
- `/collectors/health` returned `healthy` with fresh official bank price.
- `/collectors/quality` is expected to remain degraded until enough runtime fills the validation window and older failed POC runs age out.

Collector quality warm-up semantics tightened.

- Updated `/collectors/quality` so missing-run ratio is measured against elapsed runtime, not future intervals in the selected validation window.
- Added `validation_window_complete`, `window_started_at`, `elapsed_minutes`, and `expected_runs_so_far_per_collector`.
- This keeps Phase 3 validation useful while the 24-hour collector window is still accumulating.
- No new markdown files were created.
