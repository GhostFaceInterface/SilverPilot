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
- Set the Compose collector profile defaults to the MVP source batch so service recreation does not fall back to manual-only collection.
- Excluded inactive manual fallback runs from quality summaries when public collector groups exist.
- This keeps Phase 3 validation useful while the 24-hour collector window is still accumulating.
- No new markdown files were created.

Collector Phase 4 validation gate added.

- Added `GET /collectors/validation-gate` as a machine-readable readiness check.
- Gate returns `ready` only when health is healthy, quality is ok, and the selected validation window is complete.
- This does not start Phase 4 risk decisions; it only prevents manual interpretation drift while data accumulates.

Phase 3.4 audit and smoke guard tightened.

- Reviewed roadmap, memory bank, collector code, CI workflow, Docker Compose, tests, and VPS collector status.
- VPS collector health is healthy, but `/collectors/validation-gate` still blocks Phase 4 because the 24-hour quality window is not clean yet.
- Updated one-shot collector runner behavior so failed collector runs exit non-zero for smoke checks.
- Expanded manual VPS smoke workflow coverage to Fed RSS, FRED macro, collector quality, and validation gate.
- Updated stale README/architecture references without creating new markdown files.

Collector validation-window completion bug fixed locally.

- Found that `/collectors/quality` could keep `validation_window_complete=false` because it measured elapsed time from the oldest run still inside the sliding query window.
- Updated quality coverage to use relevant active collector history for elapsed validation coverage while keeping failure and missing-run metrics scoped to the selected recent window.
- Added a regression test for sustained history that exceeds the sliding window.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests/test_collectors.py`, `.venv/bin/python -m pytest apps/api/tests`, `docker compose config --quiet`, and `.venv/bin/python -m compileall apps/api/app`.
- Next: deploy the fix to VPS and re-check `/collectors/validation-gate`; remaining degraded causes should represent real collector quality issues.

Collector validation-window fix deployed and verified on VPS.

- Pushed commit `5b92e68` and pulled it on the VPS.
- Rebuilt and restarted the API and collector with the VPS `.env.production` file without printing secret values.
- VPS `/health` returned production `database: ok`.
- VPS `/collectors/validation-gate` now reports `validation_window_complete: true` and `elapsed_minutes: 1440`.
- Phase 4 remains blocked because quality is still degraded by real collector failures/missing runs, especially Stooq XAG/USD timeout from the VPS.
- Direct VPS curl checks to Stooq timed out after 20 seconds, confirming this is source/network reliability rather than the validation-window bug.
- Next: harden or replace the global XAG/USD public source before starting Phase 4.

Phase 3.5 global XAG/USD source hardening implemented locally.

- Added configurable global XAG/USD provider priority with Stooq primary, Gold-API free no-auth fallback, and optional Metals.Dev free-key fallback.
- Added Stooq timeout/retry/backoff settings and failure reason codes without fake price insertion or stale-value reuse.
- Updated `/collectors/validation-gate` to separate execution-critical blockers from context degradation.
- Execution-critical sources are Kuveyt bank silver, global XAG/USD, and USD/TRY; Fed RSS and FRED macro are context.
- Updated CI/VPS smoke to run the global XAG resolver instead of direct Stooq.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `docker compose config --quiet`, and `.venv/bin/python -m compileall apps/api/app`.
- Secret scan of touched paths found only placeholder/test key names, not secret values.

Phase 3.5 global XAG/USD hardening deployed and verified on VPS.

- Pushed commits `2cbd98d` and `5d1d7e8`, pulled them on the VPS, and rebuilt API/collector with `.env.production` without printing secrets.
- VPS global XAG resolver smoke succeeded. Stooq recorded a timeout failure, and the resolver selected `gold-api-xag-usd`.
- VPS `/collectors/validation-gate?window_hours=24&expected_interval_minutes=15` returned `status: ready`, `phase4_allowed: true`, `validation_window_complete: true`, and `selected_global_xag_source: gold-api-xag-usd`.
- Health/quality still report degraded history from Stooq/context failures and missing runs, but these are now non-blocking `degraded_reasons`.
- Phase 4 was not started.

Phase 4.1 deterministic paper-trade risk gate implemented locally.

- Added backend risk evaluation before paper-trade persistence.
- Every persisted paper trade now references a persisted risk decision.
- Missing/stale execution-critical data, excessive spread, insufficient paper cash, and insufficient paper position now create blocked decisions.
- Policy-blocked buy/sell attempts are stored as `paper_trades.action=blocked` without mutating paper cash or position.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `.venv/bin/python -m compileall apps/api/app`, and `docker compose config --quiet`.
- No real-money execution, bank automation, LLM decisioning, dashboard, or ML behavior was added.

Phase 4.1 deterministic paper-trade risk gate deployed and smoked on VPS.

- Pushed commit `f7612d9`, pulled it on the VPS, and rebuilt API/collector with `.env.production` without printing secrets.
- VPS Compose config passed, Alembic `upgrade head` completed, and `/health` returned production `database: ok` with `real_money_enabled: false`.
- VPS `/collectors/validation-gate?window_hours=24&expected_interval_minutes=15` returned `status: ready`, `phase4_allowed: true`, `validation_window_complete: true`, and execution-critical status `healthy`.
- VPS paper-trade smoke confirmed `hold` writes a `risk_decision` with `HOLD_REQUESTED`.
- VPS blocked-trade smoke confirmed high spread writes `paper_trades.action=blocked` with `SPREAD_TOO_HIGH` and leaves paper cash at `600.000000`.
- Remaining non-blocking degraded reasons are collector history/quality artifacts; Phase 4.x can continue with additional deterministic risk rules.

Phase 4.2 deterministic risk blocks implemented locally.

- Added configurable 24-hour and 7-day global XAG/USD volatility blocks.
- Added daily and weekly realized paper-loss limits.
- Added FOMO rapid-rise detection for paper buys.
- Added optional `expected_exit_price` expected-gain block for paper buys.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `.venv/bin/python -m compileall apps/api/app`, `docker compose config --quiet`, and `git diff --check`.
- Paper-trading tests now cover volatility, FOMO, loss limits, and expected-gain reason codes.
- No real-money execution, bank automation, LLM decisioning, dashboard, or ML behavior was added.

Phase 4.2 deterministic risk blocks deployed and smoked on VPS.

- Pushed commit `6499226`, pulled it on the VPS, and rebuilt API/collector with `.env.production` without printing secrets.
- VPS Compose config passed, Alembic `upgrade head` completed, and `/health` returned production `database: ok` with `real_money_enabled: false`.
- VPS `/collectors/validation-gate?window_hours=24&expected_interval_minutes=15` returned `status: ready`, `phase4_allowed: true`, and execution-critical status `healthy`.
- VPS paper-trade smoke confirmed optional `expected_exit_price` can block with `EXPECTED_GAIN_BELOW_COST`.
- The smoke blocked trade left paper cash at `600.000000`; no real-money or bank automation path was introduced.

Phase 4 risk status diagnostics implemented locally.

- Added read-only `GET /risk/status` for current thresholds, runtime risk metrics, deterministic `would_block_now` diagnostics, and recent 24-hour risk decision counts.
- Fixed realized-loss metric consumption so sold quantity/cost basis is consumed when computing loss-limit diagnostics.
- Local validation passed: `.venv/bin/python -m pytest apps/api/tests`, `.venv/bin/python -m compileall apps/api/app`, and `docker compose config --quiet`.
- No risk threshold was relaxed, and no real-money execution, bank automation, LLM decisioning, dashboard, or ML behavior was added.

Phase 4 risk status diagnostics deployed and smoked on VPS.

- Pushed commit `835caf7`, pulled it on the VPS, and rebuilt API/collector with `.env.production` without printing secrets.
- VPS Compose config passed, Alembic `upgrade head` completed, and `/health` returned production `database: ok` with `real_money_enabled: false`.
- VPS `/collectors/validation-gate?window_hours=24&expected_interval_minutes=15` returned `phase4_allowed: true` and execution-critical status `healthy`.
- VPS `/risk/status` returned configured thresholds, runtime metrics, `would_block_now: []`, and recent risk decision counts.
- Runtime metrics at smoke time were below blocking thresholds: 24h global XAG volatility `11.502771`, 7d volatility `13.869986`, FOMO rise `0.028355`, and daily/weekly realized loss `0.000000`.
