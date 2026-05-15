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

Status: complete for Phase 4 entry.

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
- MVP data source policy set to free/public-source first; paid market-data APIs are disabled.
- Added `0003_add_collector_audit_fields` migration locally for `fetched_at`, `raw_payload_hash`, and `parser_version`.
- Added local Phase 3.1 collectors for Kuveyt public silver page POC, Stooq XAG/USD CSV, and TCMB USD/TRY XML.
- Added no-cost BLS/FRED key placeholders.
- Updated strategy: FRED key is available locally and FRED is the MVP macro-series gateway; direct BLS collector is deferred.
- Classified Türkiye data as execution/risk context for bank spread, TRY conversion, local rates, inflation, and official tax rule checks.
- Approved Phase 6.5 PostgreSQL-first lightweight runtime memory in the roadmap without changing Phase 3 next steps.
- Local Phase 3.1 tests passed.
- Added GitHub Actions CI/CD workflow locally for backend tests, Compose validation, API image build, and manual VPS smoke/deploy validation.
- Phase 3.1 VPS smoke validation passed for TCMB and Stooq; Kuveyt public page parser failed safely without fake data.
- Added local Phase 3.2 Fed RSS collector for official Federal Reserve monetary policy feed.
- Fed RSS collector was deployed to VPS and inserted 15 official RSS items after one transient network retry.
- Added local Phase 3.3 FRED macro collector for configured FRED observations.
- Local tests, compile validation, and Docker Compose config passed for FRED macro collector.
- FRED macro collector was deployed to VPS and inserted 6 configured FRED observations.
- Started Phase 3.4 execution-critical bank silver source resolution.
- Updated Kuveyt official public collector to use public browser-loaded finance portal GMS data when available.
- Updated collector health policy to distinguish `healthy`, `degraded`, `blocked`, and `stale`.
- Kept manual bank-price ingestion as a visible degraded simulation fallback.
- Kuveyt official public collector was deployed to VPS and inserted a fresh bank silver price.
- Added multi-job collector runner support through `COLLECTOR_JOBS`.
- Added `GET /collectors/quality` for recent run count, failure, duplicate, and missing-run summaries.
- Added `GET /collectors/validation-gate` for machine-readable Phase 4 readiness.
- Deployed the sustained collector profile on VPS with Kuveyt, Stooq, TCMB, Fed RSS, and FRED jobs at a 900-second interval.
- Tightened collector smoke validation so one-shot runner commands exit non-zero when a collector records failed status.
- Fixed collector validation-window completion so sustained runs do not remain permanently incomplete as the 24-hour query window slides.
- Added Phase 3.5 global XAG/USD provider resolver with Stooq primary, Gold-API free no-auth fallback, and optional Metals.Dev free-key fallback.
- Added Stooq timeout/retry/backoff settings and provider failure reason codes.
- Updated Phase 4 validation gate to block on execution-critical bank/global XAG/USD/USDTRY freshness while treating Fed RSS and FRED macro as non-blocking context degradation.
- Local collector tests passed for Stooq timeout no-fake-data, fallback freshness, execution-critical blocking, context-only non-blocking behavior, and duplicate behavior.
- Deployed Phase 3.5 to VPS and verified `/collectors/validation-gate` returns `status: ready` and `phase4_allowed: true` with `gold-api-xag-usd` selected as global XAG fallback.

Next milestone:

- Continue Phase 4 risk policy.

## Phase 4

Status: in progress.

Completed:

- Started deterministic risk policy and rule engine work.
- Added paper-trade risk evaluation before paper-trade persistence.
- Every persisted paper trade now references a persisted risk decision.
- Missing/stale execution-critical data blocks buy/sell paper actions.
- High request spread, insufficient paper cash, and insufficient paper position create blocked risk decisions.
- Policy-blocked buy/sell attempts are persisted as `paper_trades.action=blocked` without mutating paper balances.
- Local validation passed: backend tests, compileall, and Docker Compose config.
- Phase 4.1 was deployed to VPS at commit `f7612d9`.
- VPS smoke passed for `/health`, `/collectors/validation-gate`, `HOLD_REQUESTED`, and `SPREAD_TOO_HIGH` blocked-trade behavior.
- Added local Phase 4.2 blocks for global XAG/USD volatility, daily/weekly realized paper-loss limits, FOMO rapid-rise behavior, and optional expected exit checks.
- Local Phase 4.2 validation passed: backend tests, compileall, Docker Compose config, and diff check.
- Phase 4.2 was deployed to VPS at commit `6499226`.
- VPS smoke passed for `/health`, `/collectors/validation-gate`, and `EXPECTED_GAIN_BELOW_COST` blocked-trade behavior with unchanged paper cash.
- Added local read-only `/risk/status` diagnostics for current thresholds, runtime metrics, market/history `would_block_now` reasons, and recent risk decision counts.
- Local validation passed for `/risk/status`: backend tests, compileall, and Docker Compose config.
- Deployed `/risk/status` to VPS at commit `835caf7`.
- VPS smoke passed for `/health`, `/collectors/validation-gate`, and `/risk/status`; runtime diagnostics returned `would_block_now: []`.
- Added local `/risk/status` global XAG source/sample diagnostics for 24-hour and 7-day threshold tuning.
- Local validation passed for source/sample diagnostics: backend tests, compileall, and Docker Compose config.
- Deployed `/risk/status` source/sample diagnostics to VPS at commit `048eb8b`.
- VPS smoke passed for `/health`, `/collectors/validation-gate`, and `/risk/status`; production diagnostics returned 24-hour and 7-day global XAG sample/source summaries.
- Added and deployed source-aware global XAG volatility/FOMO metrics so fallback/source mixing does not create synthetic risk blocks.
- Added and deployed read-only `/risk/status` threshold headroom diagnostics for Phase 4 tuning; risk thresholds and allow/block behavior are unchanged.
- Accepted the Phase 4 threshold decision to keep volatility thresholds conservative; `near_limit` remains monitor-only, and broader tuning is deferred until dashboard visibility and more evidence exist.
- OpenClaw roadmap alignment completed at documentation level: OpenClaw is mandatory for the future agent orchestration layer, while deterministic backend authority and the Phase 4/Phase 5 order remain unchanged.
- OpenClaw implementation has not started.

Next milestone:

- Build Phase 5 dashboard with risk status, threshold headroom, block reasons, collector freshness, volatility samples, selected global XAG source, and blocked-decision summaries.

## Phase 5

Status: in progress.

Completed:

- Added initial read-only Streamlit dashboard for portfolio, latest price, `/risk/status`, threshold headroom, `would_block_now`, blocked decision summaries, collector freshness, and global XAG sample diagnostics.
- Added dashboard Dockerfile, dependency file, and optional Docker Compose `dashboard` profile.
- Local dashboard container health and browser render validation passed.
- VPS dashboard deploy/smoke passed through the optional `dashboard` Compose profile.
- Snapshot review confirmed local stale dashboard data was caused by the collector profile not running.
- Local collector startup restored execution-critical freshness and `phase4_allowed=true`; FRED macro remains degraded locally without a configured key.
- Dashboard now suppresses `READY` sentinel values from validation-gate blocking reason display; fix was deployed and smoke-tested on the VPS.

Next milestone:

- Review whether Phase 5 needs small visibility polish before moving to Phase 6 foundation work.
