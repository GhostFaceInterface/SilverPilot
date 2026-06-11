---
type: project
created: 2026-05-18
updated: 2026-06-03
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

## 8. Hermes-Orchestrated Hybrid Memory & VPS Constraints (Option C - May 2026)
- **Memory-First Order (Phase 6.5 Prerequisite):** The Simplified Runtime Memory Layer (Phase 6.5) containing structured tables (`agent_memory_events`) must be built and fully deployed *before* active LLM agents (Phase 7) are launched. This guarantees agents are stateful from day one and prevents stateless prompt duplication and "AI slop".
- **Agent Port Isolation Bound:** For security and zero-trust boundary control, any LLM agents running on the production VPS must never connect directly to the PostgreSQL database ports. They must exclusively interact with the system via FastAPI HTTP endpoints (e.g., `/risk/status`, `/agent/memory`).
- **Off-VPS ML Training Rule:** To prevent resource starvation and OOM crashes on the live 4 vCPU / 6 GB RAM VPS, all machine learning model training (Phase 10 & 11) is strictly prohibited on the live VPS. Model training must run locally or on GitHub Actions runners, with only serialized weight files (.bin, .pkl) pushed to the VPS for lightweight O(1) inference.

## 9. Direct DeepSeek Integration, Custom Observability Logger & Memory Routing Execution (Phase 6 - May 2026)
- **Direct DeepSeek Gateway Integration (Phase 6.1):** Official DeepSeek API base (`https://api.deepseek.com/v1`) is directly integrated into `apps/api/app/llm/gateway.py`. The gateway wraps two core modes: `deepseek-chat` (fast, high-context, cost-effective standard agent) and `deepseek-reasoner` (R1-powered deep cognitive reasoning agent with native `reasoning_content` extraction for complex risk/financial assessments).
- **Budget Guard ($1.00 USD Hard Limit):** An automatic pre-flight and post-flight budget safety limiter (`apps/api/app/llm/budget_guard.py`) intercepts every LLM transaction. If the daily aggregated model cost exceeds $1.00 USD, further calls are blocked, raising a `BudgetExceededError` to safeguard resources.
- **Custom RAM-Free Observability Logger (Phase 6.2 & 6.3):** To avoid resource-heavy external telemetry suites (e.g., Langfuse, Zep), a lightweight native audit logging system is implemented:
  - **Telemetry Store:** Structured `llm_call_traces` PostgreSQL database table captures `prompt_tokens`, `completion_tokens`, `total_cost_usd`, `latency_ms`, `status`, and raw prompt/response details.
  - **Decorator Tracing:** A custom asynchrounous `@trace_llm` decorator isolates latency measurements, performs post-call token accounting, and automatically logs trace records to PostgreSQL.
  - **Port-Isolated Tracing:** FastAPI endpoints `/agent/trace` and `/agent/traces/stats` enable secure agent log ingestion and cost analytics without direct database connections.
- **Streamlit Observability Tab (Phase 6.4):** A beautiful, responsive visual tab (`st.tabs`) is added to the Streamlit app. It renders real-time budget cards, cost breakdown tables (by agent and by model), average response latency cards, and an interactive trace inspector to view raw prompts/responses.
- **Stateful Memory-First Port-Isolated Backend (Phase 6.5):** Implemented Pydantic schemas (`AgentMemoryCreate`/`AgentMemoryResponse`), database models (`AgentMemoryEvent`), and clean REST endpoints (`GET/POST /agent/memory`). Active agents (Phase 7) are forced to read and write state exclusively through these isolated endpoints, ensuring zero direct Postgres connections and solid state tracking.

## 10. VPS Port Isolation & Zero-Trust API Token Security Hardening (Phase 6.6 - May 2026)
- **Host Port Hardening (Strict Loopback Binding):** External host access to database (`5433`) and API (`8000`) docker containers has been restricted to the local loopback interface (`127.0.0.1`) in `docker-compose.yml`. Only the Streamlit Dashboard (`8501`) remains exposed to the public internet, routing requests to the API internally using the Docker bridge network.
- **Zero-Trust Token Gate:** Built the `verify_agent_token` FastAPI dependency checking the `X-Agent-Token` header value against `AGENT_API_TOKEN` defined in host environmental configurations. This secures all `/agent/*` endpoints (`/agent/trace`, `/agent/traces`, `/agent/traces/stats`, `/agent/memory`) against unauthenticated external requests.
- **Docker Compose Environment Alignment:** To prevent silent authentication bypass, `AGENT_API_TOKEN` is explicitly listed under the `environment` block of both the `api` and `dashboard` services in `docker-compose.yml`, ensuring environment variables are passed correctly from `.env` to the FastAPI runtime container.

## 11. Offline-First Historical Agent-Assisted Backtesting (Phase 8 - May 2026)
- **Zero-Cost High-Performance Architecture (Option A):** Historical backtesting is designed as "Offline-First" by using a pre-cached PostgreSQL historical database (`HistoricalAgentCache` table). This bypasses live LLM API call costs entirely, enabling millisecond-speed strategy simulation over thousands of bars.
- **Agent Veto Filters:** Strategy decisions (`BUY`) are filtered through historical agent decisions inside `StrategyRunner.apply_agent_filters`. Ham signals are vetoed to `HOLD` on `BEARISH` news sentiment or `REJECTED` risk critiques.
- **Lookback Tolerance Window:** A 24-hour lookback window is implemented. If no cached agent decision exists in that window, the backtester gracefully falls back to baseline deterministic decisions (avoiding cold-start crashes).
- **Argparse Python 3.14 Compatibility:** Replaced raw `%` signs with the word `"percent"` in script descriptions to prevent argparse crashes under Python 3.14.

## 12. Advanced Multi-Agent Analysis & Supreme Arbiter (Phase 12 - May 2026)
- **DeepSeek V4 Model Cascading:** Transitioned from legacy `deepseek-chat` and `deepseek-reasoner` to the official DeepSeek V4 model family:
  - **`deepseek-v4-flash`** for lightweight sentiment, news-agent, market-research, and source-reliability advisory tasks.
  - **`deepseek-v4-pro`** for deep cognitive evaluation, auditing, postmortem, and Supreme Arbiter dispute resolution.
- **Supreme Arbiter (Yüce Hakem) Pattern:** Established a centralized conflict resolution orchestrator (`orchestrator.py`) that sequences 5 expert agents. If agent decisions or advisory outputs produce opposing trade sentiments or veto recommendations, the orchestrator escalates the analysis to a `deepseek-v4-pro` arbiter instance to dynamically synthesize a unified, risk-safe resolution.
- **Port Isolation & Zero-Trust DB Interaction:** In strict compliance with TIER 0 guidelines, all new expert agents interact with the system database exclusively via FastAPI HTTP endpoints (securely wrapped in background threads using fresh `SessionLocal` contexts to avoid connection leaks) rather than direct TCP port connections.

## 13. Secure Telegram Portfolio & Diagnostics Bot (Phase 13 - May 2026)
- **Zero-Trust Chat Filtering (Secure Chat ID Lock):** Implemented strict message validation checking the sender's Chat ID against the authorized `TELEGRAM_CHAT_ID`. Non-matching IDs are logged as warnings and immediately ignored without response to prevent unauthorized data exposure.
- **Asynchronous Webhook Execution (FastAPI Background Tasks):** Created a secure `POST /agent/telegram/webhook` API endpoint that parses updates and schedules response delivery in FastAPI `BackgroundTasks`. This returns a `200 OK` to Telegram within milliseconds, preventing timeout retries.
- **Hybrid Local Long-Polling Loop:** Built a startup long-polling thread inside the FastAPI lifespan context manager (`app.main`). If `TELEGRAM_BOT_MODE == "polling"`, the system runs a polling loop locally without requiring ngrok or public VPS deployment.
- **Compact Scoped Database Sessions:** Enforced strict Port Isolation by opening and closing scoped PostgreSQL database connections (`with SessionLocal() as db:`) dynamically inside the background Telegram consumer thread, eliminating connection leaks.
- **Beautiful Markdown Response Engine:** Implemented `/durum`, `/cuzdan`, `/karzarar`, and `/ajanlar` commands to render real-time paper portfolio metrics, growth margins vs. original $600 USD balance, spot price deviations, and Supreme Arbiter verdicts in clean Telegram Markdown.

## 14. Local-IDE & Remote VPS Hybrid Developer Workflow (Phase 14 - May 2026)
- **Zero-Local-Docker Policy:** To prevent local machine CPU/RAM starvation and clean up persistent volume issues, all active Docker compose profiles (PostgreSQL, Streamlit, API, Collector) are permanently shut down and disabled on the local developer machine.
- **Isolated Local Mock Testing:** Code editing runs locally in the developer's IDE, with rapid, high-coverage testing executed using fast in-memory SQLite and mocks (`pytest apps/api/tests` passing 150/150).
- **Automated Git & Remote Deploy:** Complete VPS migration is orchestrated by a local command `./scripts/deploy.sh` which:
  1. Stages, commits, and pushes current changes to GitHub `origin main`.
  2. Securely connects to `silverpilot-vps` via SSH and pulls the latest main.
  3. Triggers `scripts/vps_smoke.sh` on the VPS to rebuild services, run Alembic migrations, test collectors, and run E2E live database tests (`verify_execution_pipeline.py`).
- **Direct VPS Edit Ban:** Direct live-patching or editing of codebase files directly on the VPS is strictly prohibited to ensure Git history consistency, prevent syntax errors, and maintain zero-trust boundaries.

## 15. Telegram Bot On-Demand Analysis & Premium Charting (Phase 15 - May 2026)
- **On-Demand Scrapers & Consensuses:** Command `/canli` runs live collectors (`collect_kuveyt_public_silver`, `collect_global_xag_usd`) synchronously, calculates strategy oylamaları (rsi, bollinger, sma_cross), triggers Supreme Arbiter resolution (`run_blended_consensus_resolution`), and compiles a live diagnostic consensus text report without triggering actual paper trades.
- **Agg Headless Chart Rendering:** Command `/analiz` queries the last 24 hours of price snapshots (preferring scraped Kuveyt silver over Yahoo fallback), plots a beautiful dark-mode chart using Matplotlib (enforcing headless backend via `matplotlib.use("Agg")` *before* importing `pyplot` to prevent window-manager crashes on headless containers), segments the time-series into 3 custom shaded vertical sessions (Sabah 00-08, Öğle-Avrupa 08-16, Akşam-Amerika 16-24), and sends the output as a photo via `BytesIO` buffer with tabular statistics.
- **Budget Adjustments & Spams Mitigation:** The daily LLM budget guard threshold `DEEPSEEK_DAILY_BUDGET_USD` was increased from `1.00` to `3.00` in `.env` to accommodate on-demand DeepSeek R1 consensus trigger requests. Anti-spam/rate-limiting bounds and missing database seed guards are recommended for future hardening.

## 16. Hermes Sentiment Agent & Yüce Hakem Veto Integration (Phase 16 - May 2026)
- **Pre-filtered Ingestion:** Pre-filters raw news items from public feeds (Kitco, Bloomberg HT, FXStreet, GCM, Fed) on precious metals or macro keywords before LLM ingestion, reducing raw news noise and saving ~90% in token overhead.
- **DeepSeek Multi-Aspect Analyzer:** Executes a single structured prompt to `deepseek-v4-pro` under the `hermes-agent` namespace to return a raw JSON array assessing each article's `sentiment` (BULLISH/BEARISH/NEUTRAL), `relevance` (0.0 to 1.0), and `speculation` clickbait risk (0.0 to 1.0).
- **Multi-Aspect Weighted Formula:** Calculations compute a weighted score in range `[-1.0, 1.0]` based on source authority:
  $$\text{article\_score} = \text{sentiment\_numeric} \times (1.0 - \text{speculation}) \times \text{relevance} \times \text{source\_weight}$$
  Where sources are mapped: Global Authority (Kitco, FXStreet, Reuters, Fed; weight = 0.5), Local Expert (GCM, Bloomberg HT; weight = 0.3), and Local Forum (Investing.com; weight = 0.2).
- **Yüce Hakem Veto Filter:** The weighted sentiment score is dynamically integrated in `StrategyRunner.apply_agent_filters`. If the score falls below `HERMES_VETO_THRESHOLD` (configurable via `.env`, default `-0.45`), `BUY` signals are overridden to `HOLD` with `AGENT_VETO_HERMES_BEARISH_NEWS`.
- **System Auditor & Unit Tests:** Registered `hermes-agent` in the `auditor-agent` inspection loop and added a thorough E2E test suite in `test_hermes_agent.py` achieving 100% correct E2E test coverage across all 159 tests.

## 17. Git Pre-Commit Formatting & Lint Hook (May 2026)
- **Lightweight Local Git Hook:** A git `pre-commit` hook is established under `.git/hooks/pre-commit`. On every git commit, it automatically runs Ruff format (`.venv/bin/ruff format`) and Ruff check (`.venv/bin/ruff check --fix`) on staged Python files and auto-stages any modified changes. This enforces absolute styling conformity before files are committed, preventing Ruff format checks from breaking GitHub Actions CI pipelines.

## 18. COMEX Off-Hours STALE_DATA Bypass Rule (May 2026)
- **Timezone-Aware Off-Hours Logic:** Implemented timezone-aware detection using `zoneinfo` ("America/New_York") to bypass the strict `STALE_DATA` trade veto during weekends (Friday 17:00 ET to Sunday 18:00 ET) and daily maintenance windows (17:00 to 18:00 ET) since data scrapers do not fetch new prices while COMEX is closed. This allows paper trading and weekend simulations to run smoothly on the latest known closing price.
- **Deterministic Testing Safety:** Added a dynamic check so that when `settings.app_env == "test"`, the bypass evaluates to `False`, safeguarding existing unit and integration tests from losing determinism.

## 19. Codex Workspace & Model Cascading (June 2026)
- **Codex Dizin İzolasyonu:** Codex'e ait tüm araç, şablon ve playybook konfigürasyonları `.codex/` dizininde izole edilmiştir.
- **Model Cascading Kuralları:**
  - Keşif/Tarama/Dosya Haritalama (`scout`, `db-investigator`, `deployment-investigator`, `test-verifier`): `gpt-5.4-mini`
  - Normal Kodlama/Hata Ayıklama (`implementation-worker`, `troubleshooter`): `gpt-5.5`
  - Ağır Muhakeme/Mimari/Risk/Final İnceleme (`architect`, `security-reviewer`, `final-reviewer`): `gpt-5.5-pro`
- **Veritabanı Erişim Politikası:** İşlemler varsayılan olarak salt-okunur (read-only) yürüyecektir. Kritik kurtarma durumlarında veritabanı üzerinde değişiklik yapılması gerektiğinde, bu değişiklikler sadece kullanıcının açık onayı ile gerçekleştirilebilir.
- **Ortak Geliştirici Hafızası:** Codex ve Antigravity sistemleri, dosya sapması (drift) ve uyuşmazlıkları önlemek için hafıza katmanı olarak ortaklaşa `.agent/memory/` dizinini (Single Source of Truth) kullanacaktır.