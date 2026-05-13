# Roadmap

This file is the canonical delivery roadmap for SilverPilot. It should describe what gets built, in what order, and which validation gates must pass before moving forward.

## Current Position

SilverPilot is in Phase 3.4: execution-critical bank silver pricing is being resolved before Phase 4. Kuveyt Türk official public page parsing now uses public browser-loaded finance portal data when available; manual bank-price fallback remains a simulation unblocker, not a production-grade source. Next is VPS smoke validation and sustained collector data-quality review.

## Non-Negotiable Rules

- No real-money trading.
- No bank automation.
- No automatic live buy/sell execution.
- Backend policy owns paper-trading decisions.
- LLM agents explain, classify, critique, or report; they do not execute trades.
- ML starts only after reliable data, risk policy, paper trading, and backtesting exist.
- Each durable fact has one canonical documentation home.

## Phase 0: Project Skeleton and Discipline

Goal: prevent project chaos before adding implementation.

Deliverables:

- Root repository structure.
- Single canonical memory bank.
- Short agent-specific spec files.
- Controlled docs structure.
- `.env.example`.
- `.gitignore`.
- Docker Compose skeleton.
- Empty API, dashboard, scripts, data, and notebooks folders.

Files:

- `README.md`
- `AGENTS.md`
- `.env.example`
- `.gitignore`
- `docker-compose.yml`
- `memory-bank/*`
- `docs/*`
- `agents/*`
- `apps/api/*`
- `apps/dashboard/*`
- `scripts/*`
- `data/.gitkeep`
- `notebooks/.gitkeep`

Validation gate:

- Documentation is short and canonical.
- No secrets are committed.
- No real-money or bank automation code exists.
- Roadmap and operating rules are present.
- Repository is committed and pushed.

Status: complete except for any user-requested documentation refinements.

## Phase 1: Backend Core

Goal: create the deterministic application backbone without LLM or ML behavior.

Deliverables:

- FastAPI application factory.
- `/health` endpoint.
- Configuration loader.
- PostgreSQL connection.
- SQLAlchemy models.
- Alembic migrations.
- Basic test setup.
- Seed script or fixture for local development.

Initial modules:

- `apps/api/app/main.py`
- `apps/api/app/core/config.py`
- `apps/api/app/core/db.py`
- `apps/api/app/models/`
- `apps/api/app/schemas/`
- `apps/api/app/services/`
- `apps/api/app/api/`
- `apps/api/alembic/`
- `apps/api/tests/`

Initial entities:

- Asset
- PriceSnapshot
- Portfolio
- PaperTrade
- PortfolioSnapshot
- RiskRule
- Signal
- Report
- AgentRun

Initial endpoints:

- `GET /health`
- `GET /portfolio`
- `GET /prices/latest`
- `GET /signals/latest`
- `GET /reports/daily/latest`

Validation gate:

- API starts locally.
- PostgreSQL starts through Docker Compose.
- Migration command succeeds.
- Tests pass.
- No LLM dependency is required.

## Phase 2: Paper Trading Engine

Goal: simulate silver trades with a virtual 600 USD balance and realistic costs.

Rules:

- `initial_balance_usd = 600`
- `real_money = false`
- asset is silver first.
- bank/provider is configurable.
- every trade is paper-only.

Calculations:

- buy price.
- sell price.
- spread.
- tax and fees.
- net cost.
- net proceeds.
- grams of silver.
- cash balance.
- portfolio value.
- realized PnL.
- unrealized PnL.

Trade actions:

- `paper_buy`
- `paper_sell`
- `hold`
- `blocked`

Validation gate:

- Buying and selling at the same market price loses money after spread and fees.
- Balance cannot go negative.
- Paper trades are audit logged.
- There is no real trading path.

## Phase 3: Data Collectors

Goal: collect data that is useful immediately and ML-ready later.

Collectors:

- BankSilverPriceCollector.
- GlobalSilverPriceCollector.
- FxRateCollector.
- GoldSilverRatioCollector.
- NewsCollector.
- FedRssNewsCollector.
- FredMacroCollector.

MVP free-source order:

1. Kuveyt Türk public silver page POC.
2. TCMB daily USD/TRY XML.
3. Stooq XAG/USD current CSV.
4. Collector health and raw payload audit.
5. Fed official RSS feeds.
6. FRED macro series when `FRED_API_KEY` is configured.

Initial FRED macro series:

- `CPIAUCSL`: U.S. CPI, BLS-origin, monthly.
- `PPIACO`: U.S. producer prices, BLS-origin, monthly.
- `UNRATE`: U.S. unemployment rate, BLS-origin, monthly.
- `FEDFUNDS`: effective federal funds rate, monthly.
- `DGS10`: 10-year Treasury constant maturity yield, daily.
- `DTWEXBGS`: nominal broad U.S. dollar index, daily dollar-strength proxy.

Deferred Phase 3.x sources:

- Direct BLS API collector. Use FRED-hosted BLS-origin series first.
- TCMB EVDS deeper Türkiye macro series after a free EVDS key is configured.
- TÜİK automated collector for CPI/PPI/confidence/labor context.
- Paid market-data API abstraction remains disabled but interface-ready.

Tables:

- `raw_bank_prices`
- `raw_global_prices`
- `raw_fx_rates`
- `raw_news`
- `raw_events`
- `price_snapshots`
- `collector_runs`

Rules:

- Raw data is append-only.
- Normalized data is stored separately.
- Collector failures are logged.
- Duplicate rows are prevented.
- Timestamps are stored in UTC.
- FRED requires a user API key but no paid market-data subscription.
- BLS direct collection is optional/backlog; no BLS key is required for MVP.
- Türkiye data supports TRY execution simulation, bank spread analysis, and local risk context.
- Türkiye data must not be treated as primary global XAG direction.

Validation gate:

- Data can be collected for at least 24 hours.
- Missing-data ratio is measurable.
- Collector run status is visible.
- Failures do not silently pass.
- Collector health is `blocked` when no execution-critical bank silver buy/sell price exists.
- Collector health is `degraded` when manual bank-price fallback is fresh but official/primary bank data is unavailable.
- Fed RSS writes official macro/news items to `raw_news` without requiring an API key.
- CI runs backend tests, Docker Compose config validation, and API image build on every push or pull request.
- VPS deploy and smoke validation can be triggered manually through GitHub Actions after required VPS secrets are configured.

### Phase 3.4: Bank Silver Price Resolution

Goal: resolve execution-critical bank silver buy/sell data before the risk engine.

Primary path:

- Kuveyt Türk official public silver page.
- Parser may read only public page content and public browser-loaded JSON.
- No login, captcha bypass, paywall bypass, anti-bot bypass, private endpoint reverse engineering, or aggressive polling.
- Current parser records GMS buy/sell from the public finance portal JSON when exposed by the official page scripts.
- Source timestamp is not provided; `observed_at` uses `fetched_at` and freshness must be enforced.

Fallback path:

- Existing `POST /collectors/manual-price` can insert manual bank prices into `raw_bank_prices`.
- Manual fallback is allowed only to unblock simulation and validation.
- Manual fallback must be visible as manual/degraded in health and reports.
- Stale manual prices must not drive future risk decisions.

Third-party candidates:

- `altin.doviz.com/kuveyt-turk/gumus`: fallback-only comparison, third-party, visible bank buy/sell table, medium ToS/stability risk, reliability 3/5.
- `altin.app/altin-fiyatlari/kuveyt-turk`: diagnostic/fallback-only, third-party, visible bank metal rows with timestamps, medium ToS/stability risk, reliability 3/5.
- `altin.in`: diagnostic only, third-party, historical snippets exist but current silver bank page stability is uncertain, reliability 2/5.
- Investing/Yahoo-style pages remain avoid/diagnostic due dynamic-page and ToS risk.

Phase 4 gate:

- Do not start Phase 4 until official Kuveyt collector is VPS-smoke-tested or manual fallback policy is accepted as temporary simulation-only input.

## Phase 4: Risk Policy and Rule Engine

Goal: prevent obviously bad or invalid paper-trading actions.

Initial rules:

- Block if spread is too high.
- Block if volatility is too high.
- Block if daily max loss is reached.
- Block if weekly max loss is reached.
- Block FOMO behavior after rapid price rises.
- Block if expected net gain does not exceed costs.
- Block if required data is missing.

Decision shape:

```json
{
  "decision": "blocked",
  "reason_code": "SPREAD_TOO_HIGH",
  "risk_level": "high",
  "confidence": 1.0
}
```

Validation gate:

- Paper trading cannot bypass risk policy.
- Every blocked decision is recorded.
- The user can see why an action was blocked.

## Phase 5: Dashboard

Goal: make system state inspectable without reading database rows manually.

Initial tool:

- Streamlit.

Later option:

- Next.js dashboard.

Views:

- Starting balance.
- Current virtual balance.
- Net PnL.
- Realized and unrealized PnL.
- Latest prices.
- Spread chart.
- Avoided or blocked trades.
- Paper trade history.
- Daily reports.
- Collector health.

Validation gate:

- System health is understandable at a glance.
- Portfolio values match trade records.
- No admin-only secrets are exposed.

## Phase 6: LLM Gateway and Observability

Goal: add controlled LLM access without uncontrolled cost or unstructured output.

Components:

- OpenRouter client.
- Optional LiteLLM proxy later.
- Langfuse tracing.
- Budget guard.
- Prompt registry.
- Structured output parser.
- Retry and timeout policy.

Rules:

- Every LLM call has a trace.
- Every LLM call has a model name.
- Every LLM call records latency and estimated cost.
- Every agent has a max token limit.
- Every agent has a daily budget limit.
- Agent output must validate against a schema.
- Core backend behavior must work if LLM providers are unavailable.

Initial budget targets:

- News Agent: daily max 0.20 USD.
- Report Agent: daily max 0.10 USD.
- Risk Agent: daily max 0.30 USD.
- Audit Agent: weekly max 1.00 USD.

Validation gate:

- LLM calls cannot happen without tracing.
- Invalid structured output is rejected or retried.
- Budget limits can block calls.
- LLM outage test passes for core backend workflows.

## Phase 6.5: Lightweight Runtime Memory Layer

Goal: give agents compact operational memory before or alongside the first agents, without adding external memory infrastructure.

This is backend-managed structured runtime memory, not LLM hidden state and not markdown. It stores compressed operational facts that help agents explain recurring issues, source reliability, and postmortem lessons.

Deliverables:

- `agent_memory_events` table.
- `source_reliability_daily` table.
- `decision_memory` table.
- optional `memory_facts` table.
- optional `memory_relations` table.
- `postmortems` table.
- memory write service.
- memory query service.
- Risk Agent context builder.
- Report Agent memory summary builder.
- memory retention policy.
- memory redaction/safety policy.

Initial event types:

- `collector_failure`
- `collector_recovered`
- `source_stale`
- `source_reliability_changed`
- `risk_decision`
- `risk_policy_override`
- `agent_disagreement`
- `news_market_link`
- `postmortem`
- `model_or_strategy_note`

Out of scope:

- raw price snapshots.
- raw HTML payloads.
- full news dumps.
- full LLM traces.
- `.env` values.
- API keys.
- SSH details.
- bank information.
- collector raw data.

Validation gate:

- Memory layer works without external services.
- Memory layer does not require Zep, Graphiti, Neo4j, FalkorDB, Cognee, Letta, LightRAG, or Mem0.
- No raw price/news payloads are written into memory tables.
- No secrets are written into memory tables.
- Agent context builders retrieve compact summaries, not full logs.
- Memory records are timestamped and auditable.
- A Risk Agent can query recent relevant memory before generating explanation.
- A Report Agent can summarize source reliability and recurring issues.
- System still works if memory query returns no results.

## Phase 7: First Agents

Goal: add the minimum useful LLM agents after deterministic records exist.

Agents:

- News Agent.
- Report Agent.
- Risk Explanation Agent.

News output:

```json
{
  "impact": "positive|negative|neutral|unknown",
  "asset": "silver",
  "confidence": 0.0,
  "summary": "",
  "source_type": "news|macro|market"
}
```

Report output:

```json
{
  "portfolio_summary": "",
  "risk_summary": "",
  "actions_taken": [],
  "actions_blocked": [],
  "next_watch_points": []
}
```

Validation gate:

- Agents do not trade.
- Agent output is schema-valid.
- Agent failure does not crash the backend.
- Reports cite internal records where possible.

## Phase 8: Backtesting

Goal: determine whether strategies beat basic alternatives after costs.

Strategies:

- do nothing.
- buy and hold.
- random trade.
- rule-based strategy.
- agent-assisted strategy.

Metrics:

- net PnL.
- max drawdown.
- win rate.
- profit factor.
- number of trades.
- average trade return.
- cost drag.
- spread loss.
- tax loss.
- buy-and-hold comparison.

Validation gate:

- Backtests include spread, tax, and fees.
- Random train/test split is not used for time series.
- A strategy that cannot beat buy-and-hold is not treated as successful.
- Buy-and-hold comparison is mandatory in every strategy report.

## Phase 9: ML Dataset Automation

Goal: create versioned datasets before training models.

Rule:

- Do not train ML models during the first 30 days of data collection unless explicitly approved.

Pipeline:

```text
raw data
-> normalized snapshots
-> feature generation
-> label generation
-> training dataset version
```

Example features:

- bank spread percent.
- XAG return over 15 minutes.
- XAG return over 1 hour.
- XAG return over 24 hours.
- USD/TRY return over 24 hours.
- volatility over 24 hours.
- volatility over 7 days.
- XAU/XAG ratio.
- news sentiment score.
- hour of day.
- day of week.

Example labels:

- net profit after 1 day.
- net profit after 3 days.
- net profit after 7 days.
- profitable after costs over 3 days.
- max drawdown over next 3 days.

Validation gate:

- No feature leakage.
- Labels use future data only where label logic requires it.
- Dataset versions are reproducible.

## Phase 10: First ML Model

Goal: test a conservative first model in paper mode only.

First model:

- LightGBMClassifier.

Initial target:

- whether a position is profitable after costs within 3 days.

Second model:

- LightGBMRegressor.

Second target:

- expected net return.

Validation gate:

- Walk-forward validation is used.
- Random split is forbidden.
- Model is compared against buy-and-hold.
- Model is used only in paper trading.

## Phase 11: Model Registry and Scheduled Training

Goal: make model lifecycle auditable.

Components:

- MLflow tracking.
- Model registry.
- Weekly training job.
- Backtest comparison.
- Champion/challenger selection.

Flow:

```text
train
-> evaluate
-> backtest
-> compare with existing champion
-> register challenger
-> manually approve promotion
```

Validation gate:

- New models do not automatically become active.
- A challenger that fails validation is rejected.
- Active model version is visible.

## Phase 12: Advanced Multi-Agent Analysis

Goal: expand analysis without giving LLMs execution authority.

Agents:

- Market Research Agent.
- News Agent.
- Risk Officer Agent.
- ML Analyst Agent.
- Report Agent.
- Auditor Agent.

Decision flow remains deterministic:

```text
data
-> features
-> rule engine
-> forecast/model
-> risk engine
-> paper trade decision
-> agent explanation
```

Validation gate:

- LLMs cannot bypass risk engine.
- Disagreements are logged.
- Strong models are used only for high-risk reviews or audits.

Backlog research:

- Advanced graph memory frameworks remain research/backlog only.
- Zep/Graphiti are excluded for now due cost and operations overhead.
- Mem0 OSS, Cognee, LightRAG, and Letta remain research-only.
- `pgvector` may be evaluated later as optional semantic retrieval inside PostgreSQL.
- The approved default memory path is Phase 6.5 custom PostgreSQL runtime memory.

## Phase 13: Production Hardening

Goal: operate reliably on a VPS.

Requirements:

- Docker Compose production profile.
- GitHub Actions CI for backend tests, Compose validation, and image build.
- Manual GitHub Actions VPS smoke/deploy job using repository secrets.
- database backup job.
- restore test.
- log rotation.
- health checks.
- alerting.
- rate limits.
- secret management.
- read-only dashboard mode.
- admin authentication.

Alerts:

- collector failure.
- LLM cost limit reached.
- database growth anomaly.
- paper-trade anomaly.
- portfolio drawdown threshold reached.

Validation gate:

- Push and pull request CI must pass before deployment work.
- VPS smoke workflow validates git pull, Compose config, container rebuild, Alembic migration, `/health`, and core collector jobs.
- Services restart cleanly after reboot.
- Backups can be restored.
- Secrets are not committed.
- Monitoring catches collector and backend failures.

## Immediate Next Step

Run the MVP collectors long enough to review freshness, duplicate behavior, and missing-data ratio. The Kuveyt public page parser still fails safely and needs either a better public bank-price source or an approved public-page parser revision. Direct BLS, TCMB EVDS, TÜİK automation, paid market-data APIs, and external graph-memory frameworks remain backlog unless explicitly approved.
