# SilverPilot Project Map

## 📂 Core Directories

- **`apps/api/`**: The FastAPI backend engine. Contains models, database configurations, services (collectors, signals, strategy runners), and test suites.
- **`apps/dashboard/`**: Streamlit visualization frontend exposing paper-trading performance and LLM agent audit traces.
- **`agents/`**: Runtime financial, sentiment, and news agents (e.g., Hermes). Must not be confused with Codex subagents.
- **`scripts/`**: Operational utility scripts (database seed, initialization, database backfill, and VPS smoke tests).
- **`data/`**: Backup datasets and SQLite test databases.
- **`docs/`**: Markdown policies regarding system constraints, risks, and contracts.

---

## 🛠️ Key Execution Paths

- **Ingestion Pipeline:**
  `apps/api/app/collectors/` -> Fetches Kuveyt Silver spot, TCMB XML, and Yahoo futures -> Database snapshots.
- **Strategy and Signals:**
  `apps/api/app/services/auto_trader.py` -> Strategy runs, computes technicals, applies Hermes sentiment vetoes, and generates execution signals.
- **Risk Assessment:**
  `apps/api/app/risk/service.py` -> Enforces daily/weekly loss caps, stale data rules, and off-hours bypass.
