# SilverPilot Clean Rebuild Roadmap

## 1. Brutal Diagnosis

The old SilverPilot failed because implementation moved faster than product definition, domain modeling, and test discipline.

- No modular architecture: collectors, indicators, strategies, risk, paper execution, ML, LLM agents, Telegram, reports, and dashboard behavior grew together.
- Telegram dependency: Telegram became part of operational flow instead of being only one notification/read client.
- Weak database design discipline: the project eventually gained many tables, but the domain was not designed first and schema growth followed implementation pressure.
- Mixed responsibilities: routes, services, agents, and scripts performed overlapping orchestration.
- Too much AI-generated slop code: many methods, markdown files, scripts, and exploratory modules survived after their purpose expired.
- No stable domain model: users, accounts, banks, instruments, quotes, orders, trades, ledger entries, regimes, and risk decisions were not treated as first-class concepts from day one.
- No phased delivery: ML, agents, Telegram, dashboard, deployment, and strategy experimentation arrived before a stable simulation core.
- ML was added too early: weekly training has no value before clean data, reliable labels, reproducible backtests, and cost-aware evaluation.
- News/Hermes lacked a clear financial interpretation model: news should produce structured risk context, not direct trading authority.
- Bank reality was under-modeled: bank buy/sell prices, spread, tax, commission, freshness, and source failure behavior must be execution-critical.
- Tests existed, but complexity grew faster than the tests could protect.

## 2. Non-Negotiable Product Definition

SilverPilot is a backend-first paper-trading simulation platform for precious metals.

It is:

- A paper-trading simulator first.
- A system for answering: "If I started with X virtual money and followed strategy S under realistic bank prices and costs, what profit or loss would I have made?"
- A backend financial simulation platform that serves JSON APIs to clients.

It is not:

- A real-money trading system.
- A bank automation system.
- A get-rich bot.
- An ML-first system.
- A Telegram-first system.

The first supported asset is silver. The first supported bank is Kuveyt Turk. Nothing else is added until that path is stable and tested.

## 3. Core Domain Model

- User: application user; key fields are id, email or external identity, status, created_at.
- VirtualAccount: a user's paper-trading account; belongs to User; key fields are base_currency, starting_balance, current_status.
- Wallet: account-level cash balances by currency; belongs to VirtualAccount; key fields are currency, available_amount, reserved_amount.
- Bank: pricing institution; key fields are name, country, status, source_policy.
- BankInstrument: bank-specific tradable quote definition; links Bank, Metal, Currency, and unit; key fields are symbol, buy_quote_field, sell_quote_field, min_trade_amount, fee_rule_id.
- Metal: precious metal such as silver or gold; key fields are code, name, default_unit.
- Currency: ISO-style currency entity; key fields are code, name, decimal_places.
- PriceQuote: raw executable bank quote; links BankInstrument; key fields are bank_buy_price, bank_sell_price, observed_at, fetched_at, source, freshness_status.
- MarketBar: OHLC-like aggregate from quotes or historical data; key fields are instrument, timeframe, open, high, low, close, quote_count, start_at, end_at.
- IndicatorSnapshot: calculated indicator values for one instrument/timeframe/bar; key fields are indicator_name, parameters, value, calculated_at, source_bar_end_at.
- MarketRegime: detected market state; key fields are regime, confidence, evidence, starts_at, confirmed_at.
- Strategy: deterministic rule set that reads bars, indicators, and regimes; key fields are name, version, parameters, enabled.
- TradeIntent: proposed action from a strategy; key fields are side, quantity or cash_amount, rationale, signal_time, strategy_run_id.
- PaperOrder: risk-approved simulated order request; key fields are side, requested_quantity, limit or market intent, status, risk_decision_id.
- PaperTrade: simulated execution at realistic bank price; key fields are side, quantity, execution_price, fees, taxes, spread_cost, executed_at.
- Position: current metal holding for a VirtualAccount and BankInstrument; key fields are quantity, average_cost, realized_pnl.
- LedgerEntry: immutable accounting movement; key fields are account_id, currency, amount, entry_type, reference_type, reference_id.
- NewsEvent: normalized news item; key fields are source, published_at, fetched_at, title, summary, affected_assets, event_type.
- MacroEvent: scheduled or observed macro event; key fields are event_type, country, importance, expected_at, actual_value, previous_value.
- RiskDecision: approve, reduce, or reject decision for a TradeIntent; key fields are decision, reasons, constraints_applied, created_at.
- PortfolioSnapshot: point-in-time account valuation; key fields are cash_value, position_value, total_value, unrealized_pnl, drawdown.

## 4. Database Design

Use PostgreSQL. Do not use a single-table design. All money and quantity fields use fixed precision numeric types in the database and Decimal in Python.

- users: stores users; indexes on email/external_id and status; retain permanently unless account deletion policy says otherwise.
- virtual_accounts: stores paper accounts; indexes on user_id and status; retain permanently for audit.
- wallets: stores per-currency cash; unique index on account_id/currency_id; retain current rows plus ledger history.
- banks: stores supported banks; unique index on bank code.
- bank_instruments: stores bank-specific metal/currency/unit quote definitions; unique index on bank_id/metal_id/currency_id/unit.
- metals: silver, gold, and future metals; unique index on code.
- currencies: TRY, USD, EUR, etc.; unique index on code.
- price_quotes: append-only executable bank quotes; indexes on bank_instrument_id/observed_at and fetched_at; retain raw quotes long-term or archive by age.
- market_bars: aggregated bars; unique index on instrument/timeframe/start_at; retain long-term for backtests.
- indicator_snapshots: calculated indicators; unique index on instrument/timeframe/indicator/parameters/bar_end_at; retain as reproducible cache.
- market_regime_snapshots: detected regimes; indexes on instrument/timeframe/confirmed_at/regime; retain long-term for audit.
- strategies: strategy definitions and versions; unique index on name/version.
- strategy_runs: every strategy evaluation; indexes on strategy_id, account_id, run_at.
- trade_intents: strategy outputs; indexes on account_id, strategy_run_id, created_at, status.
- paper_orders: risk-approved or rejected simulated orders; indexes on account_id, status, created_at.
- paper_trades: simulated executions; indexes on account_id, paper_order_id, executed_at.
- positions: current holdings; unique index on account_id/bank_instrument_id.
- ledger_entries: immutable accounting journal; indexes on account_id, created_at, reference_type/reference_id; never update in place.
- news_sources: source registry with reliability and source policy; unique index on source code.
- news_events: normalized news; indexes on source_id, published_at, affected asset fields.
- macro_events: macro calendar and observed macro data; indexes on country, event_type, expected_at.
- risk_decisions: every risk decision; indexes on trade_intent_id, decision, created_at.
- portfolio_snapshots: valuation history; indexes on account_id and captured_at; retain long-term for PnL/backtests.
- system_health_events: collector, scheduler, API, and worker health; indexes on component, status, created_at; archive older noisy data.

## 5. Service Architecture

- BankPriceProvider: fetches public bank quotes; input bank instrument; output PriceQuote candidate; must not persist or trade; test parser, stale data, and failure modes.
- KuveytTurkPriceProvider: first provider implementation; input Kuveyt Turk silver instrument; output bank buy/sell quote; must not bypass login/captcha/private endpoints; test with fixtures.
- FXRateProvider: fetches FX context; output currency pair quote; must not decide trades; test stale/missing data.
- HistoricalMarketDataProvider: fetches historical bars; output normalized bars; must not mix provider data without provenance.
- PriceCollector: schedules providers and persists quotes; must not create signals.
- BarBuilder: converts quotes to bars; must not fetch remote data.
- IndicatorService: calculates requested indicators and caches snapshots; must not run strategies.
- RegimeDetector: classifies market regime from indicators and bars; must not create orders.
- StrategyEngine: runs enabled strategies and creates TradeIntent; must not execute trades.
- RiskManager: approves, reduces, or rejects every TradeIntent; must not be bypassed.
- PaperBroker: executes approved paper orders at realistic executable prices; must not call real banks.
- PortfolioService: computes positions and valuations; must not mutate ledger directly except through approved services.
- LedgerService: writes immutable ledger entries; must not edit old entries.
- NewsCollector: collects news events; must not interpret beyond source metadata.
- NewsInterpreter: converts news to structured risk context; must not place trades.
- MacroEventService: stores macro calendar and actual values; must not trade.
- BacktestEngine: replays historical data and simulated decisions; must not mutate live paper accounts.
- ReportingService: produces PnL and audit reports; must not change state except saved report records.
- NotificationService: routes notifications; must not own business decisions.
- TelegramAdapter: reads backend outputs and sends formatted messages; must not be required for engine execution.
- REST API layer: JSON boundary for Telegram, web, mobile, and future clients.

## 6. Interfaces / Abstract Contracts

```python
class PriceProvider(Protocol):
    def fetch_quote(self, instrument: BankInstrumentRef) -> PriceQuoteDTO: ...

class IndicatorCalculator(Protocol):
    def calculate(self, bars: list[MarketBarDTO], params: dict) -> IndicatorSnapshotDTO: ...

class RegimeDetector(Protocol):
    def detect(self, context: RegimeInput) -> MarketRegimeDTO: ...

class Strategy(Protocol):
    def evaluate(self, context: StrategyContext) -> list[TradeIntentDTO]: ...

class RiskManager(Protocol):
    def evaluate(self, intent: TradeIntentDTO, context: RiskContext) -> RiskDecisionDTO: ...

class PaperBroker(Protocol):
    def execute(self, order: PaperOrderDTO, quote: PriceQuoteDTO) -> PaperTradeDTO: ...

class NotificationAdapter(Protocol):
    def send(self, message: NotificationMessage) -> NotificationResult: ...

class NewsSource(Protocol):
    def fetch(self, since: datetime) -> list[RawNewsItem]: ...

class NewsInterpreter(Protocol):
    def interpret(self, item: RawNewsItem) -> NewsEventDTO: ...
```

Telegram must depend on the backend API or service layer. The backend must never depend on Telegram. A future web or mobile app must be able to use the same API without new core trading logic.

## 7. Technical Indicator Plan

Start with:

- EMA 50
- EMA 200
- RSI 14
- ATR 14
- ADX 14
- Bollinger Band Width
- Volume or quote-count proxy if real volume is unavailable

Do not calculate every indicator. Calculate only what a strategy or regime detector requests. Cache snapshots by instrument, timeframe, indicator name, parameters, and source bar end timestamp. Avoid stale indicator bugs by requiring indicator snapshots to reference the exact bar window used. Validate calculations against a known library with deterministic fixtures.

## 8. Market Regime Detection Plan

Start rule-based, not ML.

Regimes:

- TREND_UP
- TREND_DOWN
- RANGE
- HIGH_VOLATILITY
- LOW_VOLATILITY
- NO_TRADE

Signals:

- EMA slope.
- EMA 50 / EMA 200 relationship.
- ADX threshold.
- ATR expansion.
- Bollinger Band Width.
- Price structure if feasible.

Hysteresis:

- Do not switch regime on one candle.
- Require N consecutive confirmations.
- Use cooldown after regime changes.
- Keep previous regime during uncertainty.
- Use NO_TRADE when data freshness or source quality is not acceptable.

## 9. Strategy Selection Plan

Strategies produce TradeIntent, not direct trades.

- TREND_UP: pullback long strategy using EMA + RSI + ATR.
- TREND_DOWN: no long entries or defensive mode.
- RANGE: Bollinger + RSI mean reversion.
- HIGH_VOLATILITY: reduce size or no-trade.
- LOW_VOLATILITY: watch for breakout, do not overtrade.
- NO_TRADE: no new trades.

Only one simple strategy is implemented first. Strategy selection becomes configurable after the backtest engine is stable.

## 10. Risk Management Plan

RiskManager must approve, reduce, or reject every TradeIntent.

Initial guards:

- Max position size.
- Max order size.
- Max daily loss.
- Max drawdown.
- Minimum data freshness.
- Maximum spread threshold.
- Stale price protection.
- Source divergence protection.
- Event-risk protection.
- Cooldown after loss.
- No-trade windows.
- Minimum expected edge after spread, commission, tax, and slippage.

Risk decisions must be persisted and explainable. PaperBroker must reject any order without an approving RiskDecision.

## 11. Realistic Bank Pricing Plan

Bank prices are not exchange prices. Buying uses the bank sell price. Selling uses the bank buy price.

For each bank define:

- Public price source.
- Buy price.
- Sell price.
- Spread.
- Timestamp.
- Fetch method.
- Data freshness rule.
- Failure handling.
- Legal, robots, and terms consideration.

Start with Kuveyt Turk only. Do not add Ziraat, Is Bankasi, Garanti, or any other bank until Kuveyt Turk is stable, tested, and observable.

## 12. Cost Model

Paper trading must include:

- Spread.
- Commission.
- Tax.
- Slippage approximation.
- Minimum transaction amount.
- Unit conversion.
- Currency conversion.
- Bank-specific rules.

Cost rules must be versioned or date-effective when real-world rules change. Do not hardcode a tax or commission as permanent truth without a dated source and test fixture.

## 13. News / Hermes Agent Plan

Hermes must not trade directly.

Hermes should:

- Collect news.
- Classify event type.
- Classify affected asset.
- Estimate direction bias.
- Estimate confidence.
- Estimate time horizon.
- Produce event risk flags.
- Produce structured JSON.

Hermes should not:

- Place trades.
- Override RiskManager.
- Make unsupported claims.
- Use stale news.
- Treat all news equally.

Source categories:

- Central bank sources.
- Turkish financial news.
- Global financial news.
- Commodity-specific sources.
- Economic calendar sources.

Hermes output schema:

```json
{
  "source": "string",
  "published_at": "datetime",
  "fetched_at": "datetime",
  "title": "string",
  "summary": "string",
  "event_type": "string",
  "affected_assets": ["XAG"],
  "direction_bias": "bullish|bearish|neutral|mixed|unknown",
  "confidence": 0.0,
  "time_horizon": "intraday|1d|1w|1m|unknown",
  "risk_level": "low|medium|high|unknown",
  "reasoning": "string",
  "action_recommendation": "veto|reduce_risk|no_trade|monitor|none"
}
```

The trading system uses Hermes only as veto, risk reducer, no-trade trigger, or regime confidence modifier.

## 14. ML Plan

ML is delayed.

- Phase 1: no ML; rule-based system only.
- Phase 2: collect clean labeled data.
- Phase 3: offline experiments only.
- Phase 4: ML regime classifier as advisory signal only.

ML must not be introduced before stable data collection, stable paper trading, stable backtesting, enough historical records, reliable labels, time-series validation, and transaction costs included.

## 15. Backtesting Plan

Backtest must answer: "If I started with X money on date A and followed strategy S until date B, what happened?"

Include:

- Initial cash.
- Bank selection.
- Metal selection.
- Unit selection.
- Price source.
- Spread.
- Commission.
- Tax.
- Slippage approximation.
- Signal timestamps.
- Order timestamps.
- Execution price.
- Rejected trades.
- Portfolio value curve.
- Drawdown.
- Win rate.
- Profit factor.
- Sharpe-like risk-adjusted metric if possible.
- Final PnL.

Backtests must be deterministic and reproducible from stored inputs.

## 16. API Design

All outputs are JSON. Telegram, web, and mobile clients consume the same backend output.

Initial REST resources:

- accounts
- wallets
- banks
- instruments
- prices
- indicators
- regimes
- strategies
- paper trading
- positions
- portfolio snapshots
- backtests
- reports
- news events
- system health

Mutating endpoints require explicit service-layer validation and tests. No route should contain financial formulas directly.

## 17. Telegram Plan

Telegram is only a notification/read client.

It can show:

- Wallet.
- Portfolio.
- Current prices.
- Latest regime.
- Latest strategy decision.
- Latest risk decision.
- Latest trades.
- Daily PnL.
- System health.

It must not be required for collectors, strategy runs, risk decisions, paper execution, backtests, or ledger correctness.

## 18. Testing Plan

No feature is complete without tests.

Required tests:

- Unit conversion.
- Bank price parsing.
- Spread calculation.
- Cost calculation.
- Indicator calculation.
- Regime detection.
- Strategy intent generation.
- Risk rejection.
- Paper order execution.
- Ledger correctness.
- Backtest reproducibility.
- Stale data protection.
- API response schemas.
- Telegram formatting.

Use deterministic fixtures. Money and quantity assertions must use Decimal-safe comparisons.

## 19. Observability Plan

Include:

- Structured logs.
- Health checks.
- Collector freshness.
- Last successful price fetch.
- Last successful indicator calculation.
- Last successful strategy run.
- Rejected trade reasons.
- Error counters.
- Telegram/system alerting.
- Database migration status.

Failures must be visible states, not silent empty success.

## 20. Deployment Plan

Use Docker only after local architecture is clean.

Initial deployment:

- API service.
- Worker/collector service.
- Postgres.
- Redis optional.
- Scheduler optional.

Use docker-compose for development and VPS deployment. Do not introduce Kubernetes.

## 21. Phase-by-Phase Build Plan

### Phase 0: Repository reset and project skeleton

Goal: create a clean Python backend skeleton.
Deliverables: pyproject.toml, FastAPI app, settings module, domain models, tests.
Create: silverpilot/app, tests, pyproject.toml.
Acceptance: tests pass; app imports; no trading logic.
Do not include: Docker, DB, bank scraping, Telegram, ML, Hermes.

### Phase 1: Domain model and database schema

Goal: implement first-class domain concepts and PostgreSQL schema.
Deliverables: SQLAlchemy models, Alembic baseline, schema tests.
Acceptance: migration applies locally; relationships and constraints tested.
Do not include: trading strategies.

### Phase 2: Kuveyt Turk price provider

Goal: prove public Kuveyt Turk silver quotes can be fetched legally and reliably.
Deliverables: provider interface, Kuveyt implementation, parser fixtures.
Acceptance: parser detects buy/sell/timestamp and fails visibly on bad fixtures.
Do not include: other banks.

### Phase 3: Price storage and bar builder

Goal: persist quotes and aggregate bars.
Deliverables: collector service, quote tables, bar builder.
Acceptance: duplicate handling, freshness, and quote-count bars tested.
Do not include: strategies.

### Phase 4: Indicator service

Goal: calculate requested indicators from bars.
Deliverables: indicator calculators and cache.
Acceptance: deterministic fixtures match known library output.
Do not include: every possible indicator.

### Phase 5: Rule-based regime detector

Goal: classify regimes using indicators and hysteresis.
Deliverables: regime service and snapshots.
Acceptance: trend/range/high-vol/no-trade cases tested.
Do not include: ML classifier.

### Phase 6: One simple strategy

Goal: produce TradeIntent from one strategy.
Deliverables: strategy engine, one trend-up pullback strategy.
Acceptance: intent generation and no-intent cases tested.
Do not include: direct execution.

### Phase 7: Risk manager

Goal: every intent is approved, reduced, or rejected.
Deliverables: risk rules and persisted decisions.
Acceptance: stale data, spread, drawdown, and max size rejections tested.
Do not include: bypass paths.

### Phase 8: Paper broker and ledger

Goal: execute approved orders realistically and account for them.
Deliverables: paper orders, trades, positions, ledger entries.
Acceptance: buy then sell at same quote loses money after costs; ledger balances.
Do not include: real trading.

### Phase 9: Backtest engine

Goal: answer the core product question over a date range.
Deliverables: deterministic replay engine and report output.
Acceptance: reproducible PnL, drawdown, rejected trades, and portfolio curve.
Do not include: LLM or ML.

### Phase 10: REST API

Goal: expose backend state as JSON.
Deliverables: accounts, prices, indicators, regimes, trades, backtests, reports, health endpoints.
Acceptance: schema tests and service-layer boundaries.
Do not include: frontend-specific business logic.

### Phase 11: Telegram adapter

Goal: add Telegram as a read/notification client.
Deliverables: command formatting and notification adapter.
Acceptance: Telegram can be disabled without breaking core services.
Do not include: Telegram-owned trading decisions.

### Phase 12: News/Hermes risk module

Goal: add structured event-risk context.
Deliverables: news sources, interpreter, Hermes JSON schema.
Acceptance: stale news ignored; risk flags can reduce or veto only through RiskManager.
Do not include: direct agent trading.

### Phase 13: Reporting dashboard data

Goal: expose portfolio, PnL, risk, and health data for future clients.
Deliverables: report DTOs and API endpoints.
Acceptance: web/mobile can consume same JSON.
Do not include: heavy UI before backend is stable.

### Phase 14: ML experiments

Goal: offline ML experiments after enough clean data exists.
Deliverables: dataset builder, time-series validation, advisory-only model report.
Acceptance: costs included; ablation shows value beyond rules.
Do not include: ML authority over trades.

## 22. Suggested New Folder Structure

```text
silverpilot/
  app/
    main.py
    core/
    domain/
    db/
    providers/
    collectors/
    indicators/
    regimes/
    strategies/
    risk/
    paper_trading/
    portfolio/
    news/
    backtesting/
    reporting/
    api/
    notifications/
  tests/
  migrations/
  scripts/
  docs/
```

- app/main.py: FastAPI entrypoint.
- core: settings, logging, common utilities.
- domain: pure domain models and value objects.
- db: SQLAlchemy session and persistence helpers.
- providers: external source interfaces and implementations.
- collectors: scheduled collection workflows.
- indicators: indicator calculation and cache logic.
- regimes: market regime detection.
- strategies: deterministic strategy implementations.
- risk: risk policies and decisions.
- paper_trading: paper orders, executions, positions, ledger integration.
- portfolio: valuation and snapshots.
- news: news collection and interpretation.
- backtesting: historical replay.
- reporting: PnL, audit, and portfolio reports.
- api: REST routes and schemas.
- notifications: Telegram and future adapters.
- tests: unit and integration tests.
- migrations: Alembic revisions.
- scripts: small operational scripts only.
- docs: durable design documents only after canonical files exist.

## 23. First Implementation Prompt After Reset

Use this exact prompt next:

```text
Create the clean SilverPilot project skeleton only.

Requirements:

1. Create pyproject.toml for a Python FastAPI project.
2. Create a basic FastAPI app under silverpilot/app with a health endpoint.
3. Create a settings module with environment-based configuration, but do not read or print secrets.
4. Create initial domain models as plain Python dataclasses or Pydantic models for:
   User, VirtualAccount, Wallet, Bank, BankInstrument, Metal, Currency, PriceQuote, MarketBar,
   IndicatorSnapshot, MarketRegime, Strategy, TradeIntent, PaperOrder, PaperTrade, Position,
   LedgerEntry, NewsEvent, MacroEvent, RiskDecision, PortfolioSnapshot.
5. Add focused tests for domain model construction, Decimal money/quantity handling, and basic health endpoint behavior.
6. Run the tests.
7. Commit the skeleton with:
   chore: create clean SilverPilot skeleton

Do not implement trading logic, bank scraping, indicators, ML, Hermes, Telegram, Docker, database migrations, deployment, or dashboard code in this first rebuild step.
```

## 24. Engineering Hardening Addendum

This addendum is mandatory. It exists to prevent the clean rebuild from becoming another uncontrolled implementation pile. Product scope is not enough; correctness, repeatability, and failure behavior must be locked from Phase 0.

### 24.1 Lookahead Bias Prevention

Backtests and strategy evaluations must only use data that would have been available at the simulated decision timestamp.

- A bar is usable only after its close time plus any configured ingestion delay.
- Indicators may only be calculated from closed bars that were available at `indicator_calculated_at`.
- News may not be used before the later of `published_at`, `fetched_at`, and interpreter availability.
- Macro expectations may be known before release, but actual values may only be used after the official release timestamp.
- Intraday decisions must not use final daily high, low, close, volume, or derived indicators from an unfinished day.
- Future regime labels, future trade outcomes, future drawdowns, and final backtest results must never be used as strategy inputs.
- Historical replay must fail closed if timestamp ordering is ambiguous.

### 24.2 Timestamp Model

Every time-sensitive record must distinguish when something happened, when a provider reported it, when SilverPilot saw it, and when SilverPilot used it.

- `source_event_time`: when the market, news, or macro event actually occurred, if knowable.
- `provider_reported_at`: timestamp reported by the source/provider.
- `observed_at`: quote or value observation time used by the provider.
- `fetched_at`: when SilverPilot fetched the source data.
- `stored_at`: when SilverPilot persisted the normalized record.
- `bar_start_at`: first instant covered by a market bar.
- `bar_end_at`: closing instant of a market bar.
- `indicator_calculated_at`: when the indicator snapshot was calculated.
- `decision_at`: when a strategy or risk decision was made.
- `order_created_at`: when a paper order was created.
- `executed_at`: when a paper order was simulated as executed.

All timestamps are stored in UTC. Provider-local timezones must be normalized before persistence. Backtests must use a clock abstraction and compare against these fields, not wall-clock time.

### 24.3 Data Quality Gate

Add `DataQualityService` before strategies are allowed to consume market data.

It must validate:

- stale data.
- duplicate quotes.
- missing quotes.
- zero or negative prices.
- impossible spread.
- buy/sell field inversion.
- source divergence.
- parsing failures.
- timezone normalization.
- weekend, holiday, maintenance, and bank-unavailable states.

No strategy may run on data that fails the data quality gate. Failed data quality is a first-class observable state, not an empty success.

### 24.4 Ledger Invariants

Ledger correctness is core product correctness.

- Ledger entries are append-only and immutable.
- Every successful paper trade produces ledger entries.
- Cash balances must reconcile with ledger history.
- Positions must reconcile with trades and ledger entries.
- Position quantity must never become negative.
- Buy decreases cash and increases metal position.
- Sell decreases metal position and increases cash.
- One order cannot execute twice.
- One trade cannot be posted to the ledger twice.
- Buy then immediate sell at the same quote must lose money after spread and costs.
- Paper trade creation, position update, wallet update, and ledger posting must happen in one database transaction.

### 24.5 Idempotency Rules

Every rerunnable workflow needs an idempotency key or equivalent unique constraint.

Required idempotency surfaces:

- price collection.
- bar building.
- indicator calculation.
- regime detection.
- strategy runs.
- paper order execution.
- ledger posting.
- notification sending.

Use explicit fields such as `idempotency_key`, `job_run_id`, `strategy_run_id`, `source_message_hash`, and order execution locks. The same job or order rerun must not create duplicate financial state. One approved `PaperOrder` can produce at most one successful `PaperTrade`.

### 24.6 Concurrency and Locking

Financial mutations require explicit concurrency boundaries.

- Use account-level locks for account-affecting paper execution.
- Use instrument-level locks for instrument/timeframe aggregation where needed.
- Use scheduler locks so one scheduled job cannot overlap itself.
- Permit only one active strategy run per account/instrument/timeframe.
- `PaperBroker`, `LedgerService`, wallet updates, and position updates share one transaction boundary.
- A failed transaction must leave no partial trade, ledger, wallet, or position state.

### 24.7 Backtest and Live Paper Consistency

Backtest and live paper trading must share the same core logic.

Shared components:

- `StrategyEngine`
- `RiskManager`
- cost model
- `PaperBroker` execution rules
- `LedgerService` rules
- indicator calculations
- regime detection logic

Only data source and clock implementation may differ. Backtest uses historical replay sources and simulated clocks. Live paper uses current providers and real clocks.

### 24.8 No-Trade Decision Audit

The system must persist why no trade happened, not only what happened when a trade executed.

Track at minimum:

- no signal.
- stale data.
- high spread.
- high volatility.
- event risk.
- daily loss limit.
- drawdown limit.
- insufficient balance.
- regime uncertainty.
- cooldown active.

Use `strategy_runs.decision_summary`, `risk_decisions`, or a dedicated decision audit log. Reports must answer: "Why did the bot not trade?"

### 24.9 Security and Secrets

- `.env` must never be committed.
- `.env.example` must exist once Phase 0 creates runtime configuration.
- Secrets must not appear in logs, Telegram messages, roadmap/docs, test fixtures, screenshots, or error responses.
- Use separate dev, staging, and production configuration.
- Document a secret rotation procedure before production deployment.
- Enable GitHub secret scanning if possible.
- Mutating API endpoints require authentication before SaaS or remote deployment.

### 24.10 CI and Code Quality

Phase 0 must introduce CI and code-quality checks.

Required checks:

- `pytest`
- `ruff check`
- `ruff format --check`
- type checking with `mypy` or `pyright`
- GitHub Actions workflow on pull request and push

Pre-commit is optional but recommended. No phase is accepted unless tests pass locally and in CI, unless the failure is explicitly documented as unrelated infrastructure failure.

### 24.11 Architecture Decision Records

Create `docs/adr/` and record durable architecture decisions.

Initial ADRs:

- Paper trading first.
- Python + FastAPI.
- PostgreSQL + Decimal/numeric for money and quantity.
- Telegram as adapter only.
- Rule-based regime before ML.
- Backtest/live paper shared core.
- No real-money execution in v1.

ADRs must explain the decision, context, consequences, and alternatives considered.

### 24.12 Definition of Done

A feature is not complete unless:

- it has tests.
- it has deterministic fixtures where relevant.
- failure modes are handled.
- logs are structured.
- database constraints exist if stateful.
- API schemas are tested if exposed.
- no business logic is hidden in routes.
- no TODO-driven fake implementation remains.
- no generated slop files are added without purpose.
- docs or ADRs are updated when behavior or architecture changes.

## 25. Data Quality & Backtest Correctness Rules

Data quality and backtest truthfulness are release blockers.

- Backtests must be reproducible from stored inputs, configuration, strategy version, risk version, and cost model version.
- Backtest reports must include PnL before costs and PnL after costs.
- Reports must include max consecutive losses, average trade duration, exposure time, turnover, cost as percentage of gross profit, missed trades due to risk rejection, and final PnL.
- Historical data fixtures must include missing data, duplicate data, stale data, outliers, weekend/holiday gaps, and source disagreement cases.
- Daily bars cannot be used for intraday decisions until the daily bar is complete.
- News and macro events must be replayed by availability time, not merely event date.
- Any data repair, interpolation, or fallback must be recorded in provenance and visible in reports.
- If bank prices are unavailable, the system records a bank-unavailable state and does not pretend that exchange prices are executable bank prices.

## 26. Security / Secrets / Repo Hygiene Rules

The clean rebuild must stay small and intentional.

- Keep `.env` local and ignored.
- Add `.env.example` in Phase 0 with placeholder names only.
- Do not commit generated caches, local databases, model binaries, notebooks with outputs, screenshots with secrets, or raw provider payloads containing sensitive data.
- Add `.gitignore` entries before introducing new tools that generate files.
- Keep docs canonical: one durable source per decision or contract.
- Use `docs/adr/` for major decisions and avoid long duplicate planning files.
- Add API authentication, authorization, account ownership checks, CORS policy, rate limiting, and audit logs before exposing SaaS-like remote access.
- Separate public read endpoints from mutating endpoints.
- Never log tokens, cookies, authorization headers, `.env` values, Telegram tokens, or provider credentials.

## 27. Global Definition of Done

Every phase must satisfy this checklist before moving forward:

- The scope is the smallest vertical slice that proves the phase goal.
- Tests cover happy path, failure path, and at least one edge case.
- Financial formulas use Decimal and deterministic expected values.
- Stateful behavior has database constraints or explicit idempotency controls.
- Concurrency and transaction boundaries are documented for mutations.
- Observability exists for success, failure, stale, blocked, and skipped states.
- API behavior is covered by schema tests when exposed.
- Docs or ADRs are updated for architecture-relevant changes.
- CI passes.
- No Hermes, ML, Telegram, Docker, dashboard, or multi-bank scope leaks into the first four rebuild phases.

## 28. First 4 Sprint Execution Plan

The first 30 days should prove one narrow vertical slice: Kuveyt Turk + silver + TRY + one virtual account + one simple strategy + paper trading + backtest.

### Sprint 1: Skeleton and domain discipline

- Create `src/silverpilot/` or another single chosen package layout and keep it stable.
- Add FastAPI health endpoint, settings, `.env.example`, pytest, ruff, type checking, and CI.
- Add only minimal domain/value models needed for the first slice: User, VirtualAccount, Currency, Metal, Bank, BankInstrument, Money, Quantity, PriceQuote, and MarketBar.
- Do not add fake business methods; use fields, validation, enums, and minimal constructors only.

### Sprint 2: Kuveyt Turk price feasibility and data quality

- Verify public source, robots/terms considerations, endpoint shape, rate limit risk, and whether prices are executable or indicative.
- Implement provider fixtures before live fetching.
- Add `DataQualityService` with stale, duplicate, invalid price, impossible spread, inversion, and timezone checks.
- Persist quotes only after passing quality rules.

### Sprint 3: Bars, indicators, and regime foundation

- Build quote-to-bar aggregation.
- Add EMA 50, EMA 200, RSI 14, ATR 14, ADX 14, and Bollinger Band Width only as requested calculations.
- Add timestamp-safe indicator snapshots.
- Add rule-based regime snapshots with hysteresis and NO_TRADE on uncertainty.

### Sprint 4: Shared strategy, risk, paper broker, ledger, and backtest slice

- Implement one simple strategy that creates TradeIntent only.
- Implement RiskManager guards for stale data, spread, max order size, and insufficient balance.
- Implement PaperBroker and LedgerService with transaction-safe invariants.
- Implement BacktestEngine using the same strategy, risk, cost, broker, ledger, indicator, and regime logic as live paper trading.
- Produce a first report with PnL before costs, PnL after costs, rejected/no-trade reasons, drawdown, and portfolio curve.

Nothing from Hermes, ML, Telegram, dashboard, Docker, multi-user SaaS, multi-bank support, or mobile/web UI enters these first four sprints.
