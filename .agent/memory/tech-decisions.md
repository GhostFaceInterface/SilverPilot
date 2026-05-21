---
type: project
created: 2026-05-18
updated: 2026-05-21
---

# Technical Stack & Architectural Decisions

## 1. Core Stack
- **Backend:** Python (FastAPI), PostgreSQL, SQLAlchemy 2.x, Alembic, Pydantic, httpx, tenacity. Deployed via Docker Compose.
- **Data Stack:** Pandas, Polars, DuckDB, NumPy.
- **LLM/Agent Stack:** OpenRouter (primary LLM router), Langfuse (tracing), Instructor (structured output validation). Hermes will act as the primary agent orchestration layer above the backend (OpenClaw optional).

## 2. Free Data Source Strategy
- **FRED:** MVP macro gateway (requires `FRED_API_KEY`).
- **Kuveyt Türk:** Gram Silver (GMS) public browser portal scraper (with 4-layer anomaly checks).
- **Global XAG/USD:** Yahoo Finance SI=F (Primary technical analysis).
- **USD/TRY FX:** TCMB (Central Bank of Turkey) daily XML as reference, Yahoo Finance USDTRY=X for intraday.
- **Fed RSS:** Official Fed Monetary Policy RSS feed.

## 3. Memory Boundaries (Development vs Runtime)
- **Development Memory (Markdown):** Limited strictly to `.agent/` instructions, `.agent/memory/MEMORY.md` index, and topic-specific files. No runtime logging or massive histories in markdown.
- **Runtime Memory (Database):** Compact operational tables inside PostgreSQL (`price_snapshots`, `paper_trades`, `risk_decisions`, `collector_runs`). `pgvector` will be evaluated later if semantic search is needed. No external Zep/Graphiti memory service is permitted.

## 4. Infrastructure & Access
- VPS runs Ubuntu with Docker. Alias: `silverpilot-vps` (uses `ssh silverpilot-vps`). Path: `/opt/silverpilot/SilverPilot`.
- GitHub Actions CI/CD (`.github/workflows/ci.yml`) runs API backend tests, Compose configuration validation, and API Docker image building.

## 5. Data Hardening & Validation (Phase 3.8 - May 2026)
- **Resolved Source Audit Trail:** Added `resolved_source` (VARCHAR(128)) and `is_degraded` (BOOLEAN) fields to `PriceSnapshot` and `RawBankPrice` tables. This enables robust audit trails regarding whether a price was derived from primary scraper or fallback Yahoo proxy.
- **Kuveyt Scraper Retry & Resilience:** Added a 3-retry attempt loop with a 5s delay on connection/timeout issues before resorting to Yahoo Finance fallback proxy (`yahoo_si_f`).
- **Hard Block Anomalies:** Structured parser/value errors (`CollectorError`) and critical value anomalies (Inverted spread, spread out-of-safe-range) strictly bypass Yahoo fallback and immediately trigger failed runs to preserve data integrity.
- **Global Cross-Control Validation:** Real-time mid price divergence validation comparing scraped bank silver price against Yahoo `SI=F` global prices. If mid price deviates by > 5%, a warning is recorded in the run log and `details_json` without aborting the collector pipeline.

## 6. Timeframe Isolation & Backfill Hardening (Phase 3.9 & 3.9.1 - May 2026)
- **Timeframe Isolation (Source Naming):** Daily historical backfill data is stored under isolated source `"yahoo-si-f-1d"` and timeframe `"1d"` to prevent technique indicators calculation errors on real-time 5m data.
- **Transaction Rollback Crash Safety:** Script errors in backfill trigger database rollback (`db.rollback()`) and record `failed` run status and exception error details inside a fresh database transaction block to prevent partial ingestions.
- **Single-Query O(1) Duplicate Prevention:** Replaced 500+ single-row SQL SELECT queries inside the loop with single-query pre-fetching of timestamps into Python sets for O(1) lookup.
- **Dual-Write Constraint Check:** Queries existing datetimes from both `PriceSnapshot` and `RawGlobalPrice` tables to prevent database `UniqueConstraint` errors.
- **Timezone Normalization:** Enforced explicit timezone-aware UTC datetime normalization on all pre-fetched values to guarantee consistency across PostgreSQL and SQLite test environments.

## 7. Deterministic Signal & Backtest Engine Architecture (Phase 5.5 - May 2026)
- **Purity of Calculations:** All indicator and backtest logic must be purely deterministic and mathematically isolated from external side-effects. Use pure pandas and NumPy for calculations.
- **Transactional Safety:** Database state changes (e.g., inserts to `signals`, `paper_trades`, and `risk_decisions`) during execution and test dry-runs must be fully isolated using SQLAlchemy transaction sessions, supporting complete rollbacks to prevent partial database states.
- **Non-Overlapping Signals:** The Strategy Runner enforces strict inventory state constraints. A 'BUY' signal is blocked if a position is currently open or pending execution. Expiration windows are defined for inactive signals.
- **Slippage & Tax Reality:** All backtests and paper simulations must account for transaction costs including Turkish bank-metals tax (currently 0.2% on sell transaction), bid-ask spreads, and latency slippage (modeled as a relative price drag).