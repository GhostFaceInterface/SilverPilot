---
type: reference
created: 2026-05-18
updated: 2026-05-22
---

# Project History & Milestone Archives

## 1. Deployed Infrastructure Status
- **VPS Target:** Ubuntu VPS with Docker Compose, alias `silverpilot-vps` (connected via SSH).
- **Deployment Path:** `/opt/silverpilot/SilverPilot`
- **API Status:** Live production container on VPS. `/health` returns `database: ok` and `real_money_enabled: false`.
- **Collector Status:** Active sustained Compose profile running Kuveyt, TCMB, Fed RSS, and FRED macro collectors at 900s intervals. `/collectors/validation-gate` returns `phase4_allowed: true` (Stooq/Gold-API deprecated in favor of Yahoo Finance).
- **Dashboard Status:** Streamlit container running on VPS displaying portfolio, prices, risk headroom, and blocked trade diagnostics.

## 2. Milestone Chronicle
- **Phase 0 (Setup):** Directory structures, initial git commit, memory bank setup.
- **Phase 1 (Core API):** FastAPI backend, PostgreSQL SQLAlchemy base, initial migrations, health checks, VPS seed command configuration.
- **Phase 2 (Paper Trading):** Virtual accounting services (`POST /paper-trades`, `GET /paper-trades/position`), negative balance controls, spread/fee loss calculations, and real-money portfolios rejection.
- **Phase 3 (Ingestion):** Scheduled collector runners, multi-job support, quality tracking, validation gates. Parsers developed for Kuveyt Türk (bank price), TCMB XML (USD/TRY FX), FRED API (macro), Fed RSS (news). Global sources migrating to Yahoo Finance.
- **Phase 3.8 (Kuveyt Türk Data Hardening):** Implemented database schema migration adding `resolved_source` and `is_degraded` audit trails. Hardened the Kuveyt silver scraper with 3-retry resilience, 4-tier anomaly detection (inverted spread, out-of-safe-range spread, high-deviation cross-control comparison vs Yahoo global mid-prices), and robust pytest verification (all 76 test suites verified passing).
- **Phase 4 (Risk Engine):** Safe pre-trade validation gate (blocks trades on excessive spreads, stale data, volatile XAG movement, daily realized losses, rapid FOMO triggers). Decisions are archived inside database `risk_decisions` and `paper_trades.action=blocked`.
- **Phase 5 (Dashboard Visibility):** Built and deployed read-only Streamlit dashboard to show real-time metrics, risk headroom, and blocking diagnostic variables.
- **Phase 3.9 (Yahoo Finance Daily Backfill & Timeframe Isolation):** Daily historical Yahoo Finance `SI=F` backfiller built under isolated source name `"yahoo-si-f-1d"` and timeframe `"1d"` to prevent real-time 5m technical indicator calculation corruption.
- **Phase 3.9.1 (Backfill Hardening & O(1) Performans):** Hardened the backfill script with transaction rollback crash-safety, dual-write constraint check against both price and snapshot tables, single-query pre-fetching O(1) set duplicates lookup, and timezone-aware normalizations for seamless PostgreSQL and SQLite test compatibility.
- **Phase 5.5 Hybrid Strategy & Backtest Design (Option C Approval - May 2026):** Formulated and approved the detailed architecture of the Deterministic Signal & Backtest Engine. Successfully merged Option B (Offline Backtesting with realistic transaction costs, tax, slippage, and hold rules) and Option C (Hermes-Orchestrated Hybrid Memory, forcing a prerequisite memory layer in Phase 6.5, VPS agent port isolation via FastAPI HTTP bounds, and Off-VPS machine learning training limits).
- **Phase 5.5 Local & VPS Integration (May 2026):** Fully completed and verified Strategy indicators calculations and Backtest engine locally (100% test coverage) and remotely. Successfully committed, pushed, and deployed updates to production VPS with active migrations applied and smoke checked with remote E2E Strategy & Backtest validation script (`verify_execution_pipeline.py`).
- **Phase 6 Direct DeepSeek, Premium Custom Observability & Port-Isolated Memory Layer (May 2026):** Successfully built and deployed direct DeepSeek Gateway (supporting Chat and Reasoner modes) with a hard-coded $1.00 USD Budget Guard, custom RAM-free telemetry store (`llm_call_traces` schema), async `@trace_llm` decorator, secure FastAPI trace/memory ingestion routes (`/agent/trace`, `/agent/memory`), and a premium visual Observability section in the Streamlit Dashboard (complete with latency analytics, cost breakdowns, and live trace inspection). All 110 tests validated as green, and deployed seamlessly to production.
- **Phase 8 Agent-Assisted Strategy Backtesting & Refinement (May 2026):** Fully implemented the "Offline-First" historical pre-cached strategy simulation engine. Added the `HistoricalAgentCache` database schema, ran migrations, and seeded **1008 price-correlated historical agent decisions** for time-series backtests. Upgraded `StrategyRunner` with automated veto rules (intercepting `BUY` signals based on bearish news sentiment or rejected critiques), and developed the twin comparative backtest simulator (`scripts/backtest_engine.py`) outputting a premium side-by-side performance audit sheet. Fully verified all 125 test cases via pytest, resolved Python 3.14 compatibility bugs, merged cleanly to `main`, and synchronized origin remote.
- **Phase 9 ML Dataset Automation Pipeline & Security Hardening (May 2026):** Implemented a high-performance offline ML feature and label dataset constructor (`scripts/build_dataset.py`) supporting time-series multi-table joins, Pandas-based returns, volatilities, future labels calculations, and a strict mathematically-proven zero-leakage protocol. Built and exposed secure endpoints (`POST /datasets/build`, `GET /datasets/list`) protected by `verify_agent_token` access control, and added a robust mock-history test suite (`apps/api/tests/test_dataset.py`) to verify pipeline safety and zero leakage. Performed an exhaustive Security & Quality audit (`security-auditor` & `quality-engineer` roles), confirming 100% green status across all 129 project tests with no deleted or bypassed test assets.
- **Phase 10 First ML Model & Live Inference (May 2026):** Developed the pipeline for training a LightGBM classification model predicting post-cost profitability inside 3 days. Integrated a pre-trade ML-based veto system inside the FastAPI paper trading backend that critiques signals generated by traditional strategies. Enforced the "Off-VPS Training Rule" keeping training local while enabling fast O(1) inference from pickled model weights (.pkl) on the production VPS.
- **Phase 11 Model Registry & Scheduled Training (May 2026):** Integrated MLflow for granular parameter, metric, and model registry tracking during local training runs. Implemented a champion-vs-challenger evaluation motor (`scripts/evaluate_challenger.py`) that performs deep backtests and automatically compares indicators. Added a manual model promotion CLI tool (`scripts/promote_model.py`) that packages models, stores metadata in `champion_metadata.json`, and stages files via Git. Exposed the secure `GET /api/v1/ml/model/active` FastAPI visibility endpoint protected by `verify_agent_token` token verification, supported by complete E2E unit tests. The entire test suite was fortified to 133/133 green passing tests.




