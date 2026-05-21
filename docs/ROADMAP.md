# Roadmap

This file is the canonical delivery roadmap for SilverPilot. It should describe what gets built, in what order, and which validation gates must pass before moving forward.

## Current Position

SilverPilot is in Phase 5: dashboard visibility. Initial Phase 5 work is a read-only Streamlit dashboard over existing backend endpoints. Phase 4 has deterministic paper-trade risk decisions deployed. After dashboard review, the immediate next steps are retrofitting the data collectors (Phase 3.4 through 3.9) to replace unreliable global sources with Yahoo Finance SI=F, implement a Technical Indicator Engine, add multi-layer anomaly controls for Kuveyt Türk, and establish a backfill strategy. Agent orchestration via Hermes (primary) or OpenClaw (optional) will start in Phase 6 foundation work. Real-money trading, bank automation, LLM decisions, and ML remain out of scope.

## Non-Negotiable Rules

- No real-money trading.
- No bank automation.
- No automatic live buy/sell execution.
- Backend policy owns paper-trading decisions.
- LLM agents explain, classify, critique, or report; they do not execute trades.
- Agent orchestration layer (Hermes primary, OpenClaw optional) is required.
- Agents never own deterministic trading, risk, or accounting decisions.
- Agents may only operate on sanitized backend summaries, approved APIs, and project-local skills.
- Agents cannot access production secrets, bank credentials, SSH private keys, or real-money systems.
- Random third-party skills are forbidden unless explicitly reviewed and approved.
- ML starts only after reliable data, risk policy, paper trading, and backtesting exist.
- Each durable fact has one canonical documentation home.

## Reference Sources (For Agent Verification)

- Yahoo Finance API reference: https://github.com/ranaroussi/yfinance
- pandas-ta reference: https://github.com/twopirllc/pandas-ta (Indicators: https://github.com/twopirllc/pandas-ta#indicators)
- FRED API: https://fred.stlouisfed.org/docs/api/fred/
- TCMB XML: https://www.tcmb.gov.tr/kurlar/today.xml
- Kuveyt Türk GMS: https://www.kuveytturk.com.tr/tr/doviz-ve-emtia

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
- YahooFinanceCollector (SI=F and USDTRY=X).
- FxRateCollector.
- GoldSilverRatioCollector.
- NewsCollector.
- FedRssNewsCollector.
- FredMacroCollector.

MVP free-source order:

1. Kuveyt Türk public silver page POC (PRIMARY bank).
2. Yahoo Finance SI=F (PRIMARY technical analysis).
3. Yahoo Finance USDTRY=X (Intraday USD/TRY).
4. TCMB daily USD/TRY XML (Official reference).
5. Collector health and raw payload audit.
6. Fed official RSS feeds.
7. FRED macro series when `FRED_API_KEY` is configured.

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
- `raw_global_prices` (Used for SI=F data, source="yahoo-si-f")
- `raw_fx_rates`
- `raw_news`
- `raw_events`
- `price_snapshots`
- `collector_runs`
- `technical_indicators`

Rules:

- Raw data is append-only.
- Normalized data is stored separately (`price_snapshots`).
- Collector failures are logged.
- Duplicate rows are prevented.
- Timestamps are stored in UTC.
- FRED requires a user API key but no paid market-data subscription.
- BLS direct collection is optional/backlog; no BLS key is required for MVP.
- Türkiye data supports USD execution simulation (from local TRY), bank spread analysis, and local risk context.
- Türkiye data must not be treated as primary global XAG direction.

Unit Conversion Pipeline (Before writing to `price_snapshots`):

- Yahoo SI=F (USD/troy oz) -> USD/troy oz: Direct. No conversion needed.
- Kuveyt Türk (TRY/gram) -> USD/troy oz: `bank_try_gram ÷ USDTRY × 31.1035`
- Yahoo USDTRY=X -> USD/TRY: Direct. Reference only (for Kuveyt conversion).
- TCMB -> USD/TRY: Direct. Official reference for Kuveyt conversion.
- Yahoo GC=F (USD/troy oz) -> Ratio: `GC÷SI`. Direct. Both in same unit.

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

### Phase 3.4: Bank Silver Price Resolution

Goal: resolve execution-critical bank silver buy/sell data before the risk engine.

Primary path:

- Kuveyt Türk official public silver page.
- Parser may read only public page content and public browser-loaded JSON.
- No login, captcha bypass, paywall bypass, anti-bot bypass, private endpoint reverse engineering, or aggressive polling.
- Current parser records GMS buy/sell from the public finance portal JSON when exposed by the official page scripts.
- Source timestamp is not provided; `observed_at` uses `fetched_at` and freshness must be enforced.

Fallback path:

- Fallback: Use Yahoo SI=F USD/oz directly as the bank price proxy (DEGRADED mode). No TRY conversion needed — portfolio is USD-based.
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

- Official Kuveyt collector has passed VPS smoke validation and anomaly controls.
- Multi-job collector runner exists for sustained validation.
- CI/VPS smoke must cover Kuveyt, Yahoo SI=F, TCMB, Fed RSS, FRED macro, collector health, collector quality, and validation-gate endpoints.
- Do not start Phase 4 until sustained collector validation confirms freshness, duplicate behavior, and missing-data ratio are acceptable.

### Phase 3.5: Yahoo Finance SI=F Integration

Goal: Integrate Yahoo Finance SI=F as the primary global data source for XAG.

Market Logic:
- **Futures vs Spot:** SI=F is futures. The contango/backwardation difference (0.1-0.5%) is acceptable for paper trading.
- **Market Hours:** COMEX trades Sun 18:00 - Fri 17:00 ET. Daily maintenance is 17:00-18:00 ET. Collector MUST NOT alarm `stale data` during this 1-hour maintenance window.
- **Rate Limits:** Safe frequency is 90 seconds (40 req/hour) to avoid ban (limit ~2000/hr).
- **User-Agent:** Mandatory `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36`.

Endpoints:
- 5m Intraday: `chart/SI=F?range=1d&interval=5m`
- 1h Intraday: `chart/SI=F?range=5d&interval=1h`
- 1d Daily (2 yrs): `chart/SI=F?range=2y&interval=1d`
- USDTRY=X 1h: `chart/USDTRY=X?range=5d&interval=1h`
- GC=F 1h: `chart/GC=F?range=1d&interval=1h`

### Phase 3.6: Technical Indicator Engine

Goal: Automatically calculate critical technical indicators from OHLCV price data.

Primary data source: Yahoo Finance SI=F
Library: Pure pandas (saf pandas rolling/ewm). `pandas-ta` ve `ta-lib` KULLANILMIYOR — Python 3.14+ VPS uyumluluğu için sıfır C-compilation bağımlılığı.

Calculation Pipeline (Runs every 5m SI=F bar):
1. SI=F data is already USD/troy oz. Use directly. No normalization required.
2. Fetch minimum required historical bars (e.g. 200 bars for SMA200).
3. Calculate using pure pandas (ewm for Wilder's smoothing, rolling for SMA/BB).
4. NaN Control: If insufficient data, write NULL. Do not throw an error.
5. Insert to `technical_indicators`.

Code Specification (Actual Implementation — `app/services/indicators.py`):
```python
import pandas as pd

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # df columns: high, low, close (close is USD/troy oz — SI=F native)
    # All indicators are computed in USD. No TRY conversion needed.
    # Uses pure pandas to avoid numba / pandas-ta compile dependencies on Python 3.14+.
    df = df.copy()

    # RSI 14 (Wilder's smoothing via ewm alpha=1/14)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9) via standard EMA
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd_line'] - df['macd_signal']

    # Bollinger Bands (20, 2) via rolling
    sma20 = df['close'].rolling(window=20).mean()
    rstd = df['close'].rolling(window=20).std()
    df['bb_upper_20_2'] = sma20 + (2 * rstd)
    df['bb_middle_20_2'] = sma20
    df['bb_lower_20_2'] = sma20 - (2 * rstd)

    # SMAs
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()

    # ATR 14 (True Range + Wilder's smoothing)
    h_l = df['high'] - df['low']
    h_pc = (df['high'] - df['close'].shift(1)).abs()
    l_pc = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    df['atr_14'] = tr.ewm(alpha=1/14, min_periods=14).mean()

    return df
```

Table Schema (`technical_indicators`):
```sql
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    price_snapshot_id INTEGER REFERENCES price_snapshots(id),
    bar_timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(8) NOT NULL,
    close_usd_oz NUMERIC(18,6),
    rsi_14 NUMERIC(10,4),
    macd_line NUMERIC(10,4),
    macd_signal NUMERIC(10,4),
    macd_histogram NUMERIC(10,4),
    bb_upper_20_2 NUMERIC(10,4),
    bb_middle_20_2 NUMERIC(10,4),
    bb_lower_20_2 NUMERIC(10,4),
    sma_20 NUMERIC(10,4),
    sma_50 NUMERIC(10,4),
    sma_200 NUMERIC(10,4),
    atr_14 NUMERIC(10,4),
    xau_xag_ratio NUMERIC(10,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bar_timestamp, timeframe)
);
```

Edge Cases:
- Missing Data -> write NULL.
- Market Closed -> Hash is identical -> skip insert.
- Weekend/Holiday -> Collector runs, hash identical -> skip insert.
- Gap (Sunday open) -> Normal, do not filter.
- Null Close -> Yahoo sometimes returns null -> skip bar.
- Volume 0 -> Normal in futures during illiquid hours -> do not filter.

### Phase 3.7: Intraday USD/TRY Tracking

Goal: Add intraday USD/TRY tracking alongside the daily TCMB rate.

Primary: Yahoo Finance USDTRY=X (1-hour OHLCV, free, no API key).
Reference: TCMB daily XML (existing, preserved).
Cross-control: If Yahoo USD/TRY deviates from TCMB by ±%2, trigger a warning.

### Phase 3.8: Kuveyt Türk Data Hardening

Goal: Harden the bank data collection chain against errors and swap anomalies.

Anomaly controls:
1. `buy_price > sell_price` check (if false -> BLOCK + ALERT, scraper swapped values).
2. Spread between %2 and %25? (if false -> BLOCK + ALERT).
3. Is the price within ±10% of the last 5 records? (if false -> DEGRADED).
4. Cross-control: Convert Kuveyt Türk TRY/gram to USD/oz (÷ USDTRY × 31.1035), then compare with SI=F USD/oz. Deviation > ±5% triggers ALERT.

Retry & Fallback mechanism:
- Retry 3 times, 5s intervals.
- If Kuveyt Türk scraping fails completely -> Use Yahoo SI=F USD/oz directly as the bank price proxy -> Run in DEGRADED mode. Portfolio is USD-based, no TRY conversion needed.
- Stay in DEGRADED mode until next successful scrape. Trade is allowed but risk engine logs warning.
- If Kuveyt page struct changes -> Old parser logs FAILED.

### Phase 3.9: Data Backfill Strategy

Goal: Pre-fill database with enough history to compute indicators like SMA200.

Backfill Flow:
1. BEFORE starting the 5m collector, fetch 2-year daily OHLCV for SI=F (one-time).
2. Write all bars to `raw_global_prices` and `price_snapshots`.
3. Compute all indicators and write to `technical_indicators`.
4. AFTER backfill completes, start the 5m collector.
5. On every new 5m bar, only calculate and insert the latest bar's indicators.

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

## Phase 6: LLM Gateway, Observability, and Agent Foundation

Goal: add controlled LLM access without uncontrolled cost or unstructured output, and prepare Agent orchestration via Hermes (primary) or OpenClaw (optional) without giving it access to deterministic core authority.

Components:

- OpenRouter client.
- Optional LiteLLM proxy later.
- Langfuse tracing.
- Budget guard.
- Prompt registry.
- Structured output parser.
- Retry and timeout policy.
- Agent workspace (Hermes skills).
- Project-local SilverPilot skill root.
- Tool allowlist/denylist policy.
- Sandbox policy.
- Model/provider routing policy.
- Trace/log integration plan with Langfuse or backend audit tables.
- Secrets boundary.
- Agent invocation policy.

Deliverables:

- Agent installation decision and runtime target.
- Agent workspace layout.
- Gateway/config documentation.
- Project-local SilverPilot skill root.
- Tool allowlist/denylist policy.
- Sandbox policy.
- Model/provider routing policy.
- Trace/log integration plan with Langfuse or backend audit tables.
- Secrets boundary.
- Agent invocation policy.

Rules:

- Every LLM call has a trace.
- Every LLM call has a model name.
- Every LLM call records latency and estimated cost.
- Every agent has a max token limit.
- Every agent has a daily budget limit.
- Agent output must validate against a schema.
- Core backend behavior must work if LLM providers are unavailable.
- Agents cannot read production secrets, bank credentials, SSH private keys, or real-money systems.
- Agents must use approved tools, sanitized backend summaries, and project-local SilverPilot skills.
- Agents cannot directly mutate the production database.

Initial budget targets:

- News Agent: daily max 0.05 USD.
- Report Agent: daily max 0.03 USD.
- Risk Agent: daily max 0.10 USD.
- Audit Agent: weekly max 1.00 USD.
(Costs are reduced via Hermes).

Validation gate:

- LLM calls cannot happen without tracing.
- Invalid structured output is rejected or retried.
- Budget limits can block calls.
- LLM outage test passes for core backend workflows.
- Agent can run a safe no-op project task.
- Agent can call/read only approved project surfaces.
- Agent cannot access `.env.production`.
- Agent cannot access SSH private keys.
- Agent cannot directly mutate production database.
- Outputs are schema-validated before backend use.
- Budget guard applies to LLM calls.
- All actions are logged or traceable.

## Phase 6.5: Simplified Runtime Memory Layer

Goal: give agents compact operational memory before or alongside the first agents, without adding external memory infrastructure.

This is backend-managed structured runtime memory, not LLM hidden state and not markdown. It stores compressed operational facts that help agents explain recurring issues, source reliability, and postmortem lessons.

Deliverables:

- `agent_memory_events` table.
- `source_reliability_daily` table.
- `decision_memory` table.
- basic FastAPI endpoint for memory queries.
- Risk Agent context builder.
- Report Agent memory summary builder.
- Agent memory context adapter.
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
- `postmortem` (merged into decision_memory)
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
- memory_facts and memory_relations (moved to backlog).

Validation gate:

- Memory layer works without external services.
- Memory layer does not require external tools (Zep, etc).
- No raw price/news payloads are written into memory tables.
- No secrets are written into memory tables.
- Agent context builders retrieve compact summaries, not full logs.
- Memory records are timestamped and auditable.
- A Risk Agent can query recent relevant memory before generating explanation.
- A Report Agent can summarize source reliability and recurring issues.
- Runtime memory provides compact operational context to agents.
- Agents read memory through the basic FastAPI endpoint.
- Agents do not write arbitrary raw memory.
- Memory write operations must use the approved backend memory write service.
- System still works if memory query returns no results.

## Phase 7: First Agents

Goal: add the minimum useful Hermes-backed agents after deterministic records, dashboard visibility, LLM gateway boundaries, and runtime memory boundaries exist.

Agents:

- SilverPilot News Agent (Hermes).
- SilverPilot Report Agent (Hermes).
- SilverPilot Risk Agent (Hermes).

Deliverables:

- Project-local skill: `~/.hermes/skills/silverpilot/news-analysis/SKILL.md`.
- Project-local skill: `~/.hermes/skills/silverpilot/risk-explanation/SKILL.md`.
- Project-local skill: `~/.hermes/skills/silverpilot/reporting/SKILL.md`.
- Project-local skill: `~/.hermes/skills/silverpilot/source-reliability/SKILL.md`.

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
- Agent task logs are auditable.

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

Goal: expand the Agent orchestration layer without giving LLMs or agents execution authority.

Agents:

- Agent Market Research.
- Agent News.
- Agent Risk Officer.
- Agent ML Analyst.
- Agent Report.
- Agent Auditor.
- Agent Source Reliability Analyst.
- Agent Postmortem.

Decision flow remains deterministic:

```text
data
-> features
-> rule engine
-> forecast/model
-> risk engine
-> paper trade decision
-> Agent explanation/critique/report
```

Validation gate:

- Agents cannot bypass risk engine.
- Agents cannot perform real trading.
- Agents cannot access bank credentials.
- Agent disagreements are logged.
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

Immediate next is retrofitting the data collectors (Phase 3.4 through 3.9). We will introduce the Yahoo Finance collector for SI=F and USDTRY=X, implement the Technical Indicator Engine with Backfill strategies, and harden the Kuveyt Türk collection with 4-layer anomaly controls. Once the data pipeline is fully hardened, we will implement Phase 6 Hermes integration and Phase 6.5 Simplified Runtime Memory before building the first Agents. Direct BLS, TCMB EVDS, TÜİK automation, paid market-data APIs, and external graph-memory frameworks remain backlog unless explicitly approved.
