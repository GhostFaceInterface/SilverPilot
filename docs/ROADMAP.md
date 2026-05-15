# Roadmap

This file is the canonical delivery roadmap for SilverPilot. It should describe what gets built, in what order, and which validation gates must pass before moving forward.

## Current Position

SilverPilot is entering Phase 5: dashboard visibility. Phase 3.5 is verified: the 24-hour validation-window bug is fixed, global XAG/USD no longer depends on Stooq alone, and `/collectors/validation-gate` has reported `phase4_allowed=true`. Phase 4 has deterministic paper-trade risk decisions, and Phase 4.2 is deployed and smoke-tested on the VPS. Phase 4 threshold policy is accepted as conservative by default; near-limit diagnostics alone are not a reason to relax volatility thresholds. Initial Phase 5 work is a read-only Streamlit dashboard over existing backend endpoints. OpenClaw is mandatory for the future agent orchestration layer, but implementation starts later in Phase 6 foundation work. Real-money trading, bank automation, LLM decisions, and ML remain out of scope.

## Non-Negotiable Rules

- No real-money trading.
- No bank automation.
- No automatic live buy/sell execution.
- Backend policy owns paper-trading decisions.
- LLM agents explain, classify, critique, or report; they do not execute trades.
- OpenClaw is mandatory for the agent orchestration layer.
- OpenClaw never owns deterministic trading, risk, or accounting decisions.
- OpenClaw agents may only operate on sanitized backend summaries, approved APIs, and project-local skills.
- OpenClaw cannot access production secrets, bank credentials, SSH private keys, or real-money systems.
- Random third-party OpenClaw/ClawHub skills are forbidden unless explicitly reviewed and approved.
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
3. Global XAG/USD resolver: Stooq current CSV primary, Gold-API free no-auth JSON approved fallback, optional Metals.Dev free API-key fallback when configured.
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
- `/collectors/quality` summarizes run count, failures, duplicates, and missing-run ratio.
- `/collectors/validation-gate` gives a machine-readable Phase 4 readiness check.
- Failures do not silently pass.
- Collector health is `blocked` when no execution-critical bank silver buy/sell price exists.
- Collector health is `degraded` when manual bank-price fallback is fresh but official/primary bank data is unavailable.
- Fed RSS writes official macro/news items to `raw_news` without requiring an API key.
- CI runs backend tests, Docker Compose config validation, and API image build on every push or pull request.
- VPS deploy and smoke validation can be triggered manually through GitHub Actions after required VPS secrets are configured.
- One-shot collector smoke commands must fail the process when a collector records failed status.

### Phase 3.5: Global XAG/USD Source Hardening

Goal: remove single-source dependence on Stooq before Phase 4.

Provider policy:

- `GlobalSilverPriceProvider` normalizes source, symbol, price, currency, unit, observed/fetched timestamps, optional bid/ask, raw payload hash, parser version, and reliability metadata.
- `GLOBAL_XAG_SOURCE_PRIORITY` controls provider order.
- `stooq_xag_usd` remains the public CSV primary but has configurable timeout, retry, and backoff.
- `gold-api-xag-usd` is an approved free no-auth JSON fallback.
- `metals-dev-silver-spot` is optional and disabled unless `METALS_DEV_API_KEY` is configured for a no-cost tier.
- Failed providers record failed collector runs with reason codes such as `TIMEOUT`, `HTTP_ERROR`, `PARSE_ERROR`, and `STALE_DATA`.
- Failed or stale providers must not write fake prices or reuse the last successful value as fresh.

Gate policy:

- Execution-critical sources are Kuveyt bank silver buy/sell, global XAG/USD, and USD/TRY.
- Context sources are Fed RSS and FRED macro series.
- Missing/stale execution-critical data blocks Phase 4.
- Context failures degrade readiness output but do not block Phase 4 by themselves.
- Stooq failure does not block Phase 4 when an approved global XAG fallback is fresh.
- Manual global XAG fallback is allowed only as a visible simulation unblocker and must be fresh.

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

- Official Kuveyt collector has passed VPS smoke validation.
- Multi-job collector runner exists for sustained validation.
- CI/VPS smoke must cover Kuveyt, global XAG resolver, TCMB, Fed RSS, FRED macro, collector health, collector quality, and validation-gate endpoints.
- Do not start Phase 4 until sustained collector validation confirms freshness, duplicate behavior, and missing-data ratio are acceptable.

## Phase 4: Risk Policy and Rule Engine

Goal: prevent obviously bad or invalid paper-trading actions.

Current Phase 4 implementation:

- Paper-trading now creates a persisted `risk_decisions` row for every accepted trade record.
- `paper_trades.risk_decision_id` is populated for allowed, hold, user-blocked, and policy-blocked paper records.
- Missing or stale execution-critical data blocks buy/sell actions with `MISSING_DATA` or `STALE_DATA`.
- Spread above `RISK_MAX_SPREAD_PERCENT` blocks with `SPREAD_TOO_HIGH`.
- Source-aware 24-hour and 7-day global XAG/USD volatility above configured thresholds blocks with `VOLATILITY_TOO_HIGH`.
- Daily and weekly realized paper-loss limits block with `DAILY_LOSS_LIMIT_REACHED` or `WEEKLY_LOSS_LIMIT_REACHED`.
- Source-aware rapid global XAG/USD rises block paper buys with `FOMO_RISK`.
- Optional `expected_exit_price` can block paper buys with `EXPECTED_GAIN_BELOW_COST`.
- Insufficient paper cash blocks with `INSUFFICIENT_CASH` and records a blocked paper-trade audit row.
- Insufficient paper position blocks with `POSITION_LIMIT_REACHED`.
- `POST /paper-trades` response includes the deterministic risk decision.
- `GET /risk/status` exposes threshold configuration, runtime metrics, threshold headroom diagnostics, `would_block_now` diagnostics, recent risk decision counts, and global XAG source/sample/range diagnostics for threshold tuning.

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

Pending Phase 4.x:

- Keep `RISK_MAX_GLOBAL_XAG_VOLATILITY_24H` / `RISK_MAX_24H_VOLATILITY_PERCENT`, `RISK_MAX_7D_VOLATILITY_PERCENT`, and related volatility thresholds conservative for now.
- Treat `/risk/status` `threshold_headroom` as monitoring/diagnostic output only.
- Do not relax thresholds because of `near_limit` alone; tune only for a critical bug or clearly incorrect blocking behavior.
- Defer broader threshold tuning until Phase 5 dashboard visibility, longer runtime evidence, backtesting, and buy-and-hold versus blocked-trade comparison exist.
- Add richer strategy target inputs if expected-return checks need more than `expected_exit_price`.

## Phase 5: Dashboard

Goal: make system state inspectable without reading database rows manually.

Status: in progress. Initial read-only Streamlit dashboard exists locally and is deployed/smoke-tested on the VPS.

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
- `/risk/status` summary.
- `threshold_headroom`.
- `would_block_now`.
- 24-hour global XAG volatility.
- 7-day global XAG volatility.
- Spread percent.
- Blocked trade count.
- `reason_code` distribution.
- Avoided or blocked trades.
- Paper trade history.
- Recent blocked decisions.
- Volatility samples.
- Collector freshness.
- Selected global XAG source.
- Daily reports.
- Collector health.

Validation gate:

- System health is understandable at a glance.
- Portfolio values match trade records.
- No admin-only secrets are exposed.
- Dashboard is read-only and does not create trades, mutate balances, or change risk policy.

## Phase 6: LLM Gateway, Observability, and OpenClaw Foundation

Goal: add controlled LLM access without uncontrolled cost or unstructured output, and prepare OpenClaw as the mandatory future agent orchestration layer without giving it access to deterministic core authority.

Components:

- OpenRouter client.
- Optional LiteLLM proxy later.
- Langfuse tracing.
- Budget guard.
- Prompt registry.
- Structured output parser.
- Retry and timeout policy.
- OpenClaw Gateway/workspace configuration.
- Project-local SilverPilot skill root.
- OpenClaw tool allowlist/denylist policy.
- OpenClaw sandbox policy.
- OpenClaw model/provider routing policy.
- OpenClaw trace/log integration plan with Langfuse or backend audit tables.
- OpenClaw secrets boundary.
- OpenClaw agent invocation policy.

Deliverables:

- OpenClaw installation decision and runtime target.
- OpenClaw workspace layout.
- OpenClaw gateway/config documentation.
- Project-local SilverPilot skill root.
- OpenClaw tool allowlist/denylist policy.
- OpenClaw sandbox policy.
- OpenClaw model/provider routing policy.
- OpenClaw trace/log integration plan with Langfuse or backend audit tables.
- OpenClaw secrets boundary.
- OpenClaw agent invocation policy.

Rules:

- Every LLM call has a trace.
- Every LLM call has a model name.
- Every LLM call records latency and estimated cost.
- Every agent has a max token limit.
- Every agent has a daily budget limit.
- Agent output must validate against a schema.
- Core backend behavior must work if LLM providers are unavailable.
- OpenClaw cannot read production secrets, bank credentials, SSH private keys, or real-money systems.
- OpenClaw must use approved tools, sanitized backend summaries, and project-local SilverPilot skills.
- OpenClaw cannot directly mutate the production database.

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
- OpenClaw can run a safe no-op project task.
- OpenClaw can call/read only approved project surfaces.
- OpenClaw cannot access `.env.production`.
- OpenClaw cannot access SSH private keys.
- OpenClaw cannot directly mutate production database.
- OpenClaw outputs are schema-validated before backend use.
- Budget guard applies to OpenClaw-triggered LLM calls where applicable.
- All OpenClaw actions are logged or traceable.

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
- OpenClaw memory context adapter.
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
- Runtime memory provides compact operational context to OpenClaw agents.
- OpenClaw agents read memory through the approved backend memory query service.
- OpenClaw agents do not write arbitrary raw memory.
- Memory write operations must use the approved backend memory write service.
- System still works if memory query returns no results.

## Phase 7: First OpenClaw-Backed Agents

Goal: add the minimum useful OpenClaw-backed agents after deterministic records, dashboard visibility, LLM gateway boundaries, and runtime memory boundaries exist.

Agents:

- OpenClaw News Agent.
- OpenClaw Report Agent.
- OpenClaw Risk Explanation Agent.

Deliverables:

- Proposed project-local skill: `skills/silverpilot-news-analysis/SKILL.md`.
- Proposed project-local skill: `skills/silverpilot-risk-explanation/SKILL.md`.
- Proposed project-local skill: `skills/silverpilot-reporting/SKILL.md`.
- Proposed project-local skill: `skills/silverpilot-source-reliability/SKILL.md`.

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
- Agents do not mutate DB directly.
- Agents use project-local SilverPilot skills.
- Agent output is schema-valid.
- Agent failure does not crash the backend.
- Reports cite internal records where possible.
- OpenClaw task logs are auditable.

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

## Phase 12: Advanced OpenClaw Multi-Agent Analysis

Goal: expand OpenClaw as the mandatory advanced agent orchestration layer without giving LLMs or agents execution authority.

Agents:

- OpenClaw Market Research Agent.
- OpenClaw News Agent.
- OpenClaw Risk Officer Agent.
- OpenClaw ML Analyst Agent.
- OpenClaw Report Agent.
- OpenClaw Auditor Agent.
- OpenClaw Source Reliability Analyst.
- OpenClaw Postmortem Agent.

Decision flow remains deterministic:

```text
data
-> features
-> rule engine
-> forecast/model
-> risk engine
-> paper trade decision
-> OpenClaw agent explanation/critique/report
```

Validation gate:

- OpenClaw cannot bypass risk engine.
- OpenClaw cannot perform real trading.
- OpenClaw cannot access bank credentials.
- OpenClaw disagreements are logged.
- Strong models are used only for high-risk reviews or audits.
- Agent recommendations are advisory unless backend policy validates them.
- Multi-agent outputs are summarized into structured backend records.

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

Immediate next is Phase 5 dashboard visibility. Phase 4 threshold policy keeps conservative volatility defaults; `near_limit` output is monitored but does not trigger automatic tuning. Threshold tuning is deferred until dashboard visibility and more runtime evidence exist unless there is a critical bug or clearly incorrect blocking behavior. OpenClaw is mandatory for the agent layer, but implementation starts later in Phase 6 foundation work after dashboard and LLM gateway boundaries are ready. After dashboard and LLM gateway foundation, OpenClaw workspace, project-local skills, sandbox policy, secrets boundaries, and auditability will be implemented. Direct BLS, TCMB EVDS, TÜİK automation, paid market-data APIs, and external graph-memory frameworks remain backlog unless explicitly approved.
