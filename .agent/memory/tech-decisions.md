---
type: project
created: 2026-05-18
updated: 2026-05-19
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