# Active Context

## Current Phase

Phase 3: free/public-source data collectors in progress.

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
- VPS collector profile is running with Kuveyt, Stooq, TCMB, Fed RSS, and FRED jobs every 900 seconds.
- VPS FRED macro smoke test passed; 6 configured FRED observations were inserted.
- FRED API key is available in local development env and FRED is the preferred no-cost macro-series gateway for MVP.
- Direct BLS API registration is deferred; BLS-origin CPI/PPI/labor series should be pulled through FRED first when available.
- Türkiye local data is classified as execution/risk context for TRY execution, bank spread analysis, and local macro context, not as global silver direction.
- Phase 6.5 lightweight PostgreSQL runtime memory is approved for later roadmap work.
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
- Run MVP collectors long enough to review freshness and missing-data ratio; keep direct BLS, TCMB EVDS, and TÜİK automation in optional/backlog unless explicitly enabled.
- Run sustained collector validation with multi-job runner now that the Kuveyt official public finance-portal parser passed VPS smoke.
- Keep CI/VPS smoke aligned with all MVP collector jobs and `/collectors/validation-gate`.
- Keep Phase 6.5 runtime memory behind the current collector deployment/Fed RSS/FRED sequence.
- Run collector long enough to measure freshness and missing data.
- Keep VPS-local `.env.production` secrets out of git and markdown.
- Ignore editor swap files created while editing production env files.

## Next Step

Let the VPS collector run through a sustained validation window, then review `/collectors/health` and `/collectors/quality` for freshness, duplicate behavior, failures, and missing-data ratio. Keep BLS direct disabled for MVP unless explicitly re-approved.
