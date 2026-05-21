---
type: reference
created: 2026-05-18
updated: 2026-05-21
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
