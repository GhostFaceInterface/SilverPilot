# Active Context

## Current Phase

Phase 4: risk policy and rule engine in progress.

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
- Phase 3.1 audit fields exist locally for raw collector tables: `fetched_at`, `raw_payload_hash`, and `parser_version`.
- Phase 3.1 local collectors exist for Kuveyt public silver page POC, Stooq XAG/USD CSV, and TCMB USD/TRY XML.
- Local tests validate Phase 3.1 parser/storage behavior.
- Phase 3.1 VPS smoke validation passed for TCMB and Stooq; Kuveyt public parser failed safely without fake data.
- Phase 3.2 Fed RSS collector exists and writes official Fed items to `raw_news`.
- VPS Fed RSS smoke test passed after a transient network failure retry; 15 Fed RSS items were inserted.
- Phase 3.3 FRED macro collector exists and writes configured FRED observations to `raw_events`.
- Phase 3.4 bank silver source resolution is implemented and VPS-smoke-tested.
- Kuveyt Türk official public page parser now targets public browser-loaded finance portal GMS data when available.
- VPS Kuveyt collector smoke passed with fresh `kuveyt-public-silver-page` bank price.
- Manual bank-price ingestion remains a simulation fallback and must show as degraded/manual, not production-grade.
- Collector runner supports comma-separated `COLLECTOR_JOBS` and defaults the collector profile to the MVP source batch.
- Collector quality endpoint exists at `GET /collectors/quality`.
- Collector validation gate exists at `GET /collectors/validation-gate` to decide when Phase 4 can start.
- One-shot collector runner commands now fail the process when a collector records failed status, so smoke checks cannot silently pass failed collectors.
- Collector quality validation window completion was fixed and deployed so sustained runs do not remain permanently incomplete as the 24-hour query window slides.
- VPS `/collectors/validation-gate` now reports `validation_window_complete: true` and `elapsed_minutes: 1440`.
- Phase 3.5 global XAG/USD source hardening is implemented and deployed.
- Global XAG/USD now uses a configurable resolver: Stooq primary, Gold-API free no-auth fallback, optional Metals.Dev free-key fallback.
- Stooq timeout/failure records explicit reason codes and writes no fake global price.
- Phase 4 gate now separates execution-critical sources from context sources.
- Execution-critical sources are Kuveyt bank silver, global XAG/USD, and USD/TRY; Fed RSS and FRED macro are context and degrade but do not block by themselves.
- VPS collector profile now uses the `global-xag-usd` resolver path.
- VPS `/collectors/validation-gate` reports `status: ready`, `phase4_allowed: true`, and `selected_global_xag_source: gold-api-xag-usd`.
- Health/quality still show degraded history from Stooq/context failures and missing runs, but they are non-blocking degraded reasons.
- Phase 4.1 deterministic paper-trade risk gate is implemented, deployed, and smoke-tested on VPS.
- Paper-trade persistence now creates and references a `risk_decisions` row.
- Missing/stale execution-critical data, high spread, insufficient paper cash, and insufficient paper position create blocked risk decisions.
- Policy-blocked buy/sell attempts are stored as `paper_trades.action=blocked` without mutating paper balances.
- Local Phase 4.1 validation passed: backend tests, compileall, and Docker Compose config.
- VPS Phase 4.1 smoke passed: `/health` is ok, `/collectors/validation-gate` is ready with `phase4_allowed: true`, hold returns `HOLD_REQUESTED`, and excessive spread returns `SPREAD_TOO_HIGH` without changing paper cash.
- Phase 4.2 deterministic risk blocks are implemented, deployed, and smoke-tested on VPS for volatility, daily/weekly realized loss, FOMO, and optional expected exit checks.
- Read-only `/risk/status` is implemented, deployed, and smoke-tested on VPS for Phase 4 threshold tuning diagnostics.
- `/risk/status` reports configured thresholds, runtime metrics, threshold headroom, global XAG source/sample diagnostics, market/history `would_block_now` reasons, and recent risk decision counts.
- VPS `/risk/status` source-diagnostics smoke returned `would_block_now: []` and showed 24-hour global XAG samples from Stooq plus Gold-API fallback.
- Phase 4 source-aware global XAG volatility/FOMO risk metrics are implemented, deployed, and smoke-tested on VPS.
- Phase 4 `/risk/status` threshold headroom diagnostics are implemented, deployed, and smoke-tested on VPS.
- Phase 4 threshold decision is accepted: keep volatility thresholds conservative; `near_limit` is monitor-only and not an automatic tuning trigger.
- VPS FRED macro smoke test passed; 6 configured FRED observations were inserted.
- FRED API key is available in local development env and FRED is the preferred no-cost macro-series gateway for MVP.
- Direct BLS API registration is deferred; BLS-origin CPI/PPI/labor series should be pulled through FRED first when available.
- Türkiye local data is classified as execution/risk context for TRY execution, bank spread analysis, and local macro context, not as global silver direction.
- Phase 6.5 lightweight PostgreSQL runtime memory is approved for later roadmap work.
- OpenClaw is mandatory for the future agent layer, after dashboard, LLM gateway, and runtime memory boundaries are ready.
- OpenClaw will be an orchestration layer above the deterministic backend, not a replacement for collectors, risk engine, paper trading, or accounting.
- Zep/Graphiti are not used; no external memory service is required.
- GitHub Actions CI/CD workflow exists locally for backend tests, Compose validation, API image build, and manual VPS smoke/deploy validation.
- VPS runner one-shot validation passed.
- VPS `GET /collectors/health` returns `ok`.
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

- Configure GitHub repository secrets before running manual VPS smoke workflow.
- Build Phase 5 dashboard with `/risk/status`, `threshold_headroom`, `would_block_now`, blocked-decision counts, reason-code distribution, volatility samples, collector freshness, and selected global XAG source.
- Keep OpenClaw implementation for Phase 6 foundation; do not move it ahead of Phase 4 tuning or Phase 5 dashboard.
- Keep CI/VPS smoke aligned with all MVP collector jobs and `/collectors/validation-gate`.
- Keep Phase 6.5 runtime memory behind the current collector deployment/Fed RSS/FRED sequence.
- Run collector long enough to measure freshness and missing data.
- Keep VPS-local `.env.production` secrets out of git and markdown.
- Ignore editor swap files created while editing production env files.

## Next Step

Next: build Phase 5 dashboard visibility. Phase 4 volatility thresholds stay conservative unless a critical bug or clearly incorrect block appears. OpenClaw starts later in Phase 6 foundation work after safe boundaries are documented and implemented. Keep BLS direct disabled for MVP unless explicitly re-approved.
