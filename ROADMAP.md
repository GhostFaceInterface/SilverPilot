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

Only silver and Kuveyt Turk are implemented in the first vertical slice. However, domain models, interfaces, value objects, and service boundaries must remain bank-agnostic and metal-agnostic from Phase 0. Nothing else is implemented until that path is stable and tested.

## 3. Core Domain Model

- User: application user; key fields are id, email or external identity, status, created_at.
- VirtualAccount: a user's paper-trading account; belongs to User; key fields are base_currency, execution_venue_id, allowed_execution_instrument_ids, starting_balance, current_status.
- Wallet: account-level cash balances by currency; belongs to VirtualAccount; key fields are currency, available_amount, reserved_amount.
- Bank: pricing institution; key fields are name, country, status, source_policy.
- BankInstrument: bank-specific tradable quote definition; links Bank, Metal, Currency, and unit; key fields are symbol, buy_quote_field, sell_quote_field, min_trade_amount, fee_rule_id.
- Metal: precious metal such as silver or gold; key fields are code, name, default_unit.
- Currency: ISO-style currency entity; key fields are code, name, decimal_places.
- PriceQuote: raw executable bank quote; links BankInstrument; key fields are bank_buy_price, bank_sell_price, observed_at, fetched_at, source, freshness_status.
- MarketBar: OHLC-like aggregate from quotes or historical data; key fields are instrument_type (`reference` or `execution`), instrument_id, source, timeframe, open, high, low, close, quote_count, bar_start_at, bar_end_at.
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
- units: stores gram, ounce, and future units; unique index on unit code.
- unit_conversion_rules: versioned Decimal conversion rules such as ounce-to-gram; indexes on from_unit_id, to_unit_id, effective_from.
- execution_venues: stores venues where paper execution is simulated, initially banks; indexes on venue_type and status.
- reference_market_instruments: stores signal/reference instruments such as XAGUSD or SI=F; unique index on symbol/source.
- execution_instruments: stores executable paper instruments tied to an execution venue, unit, metal, and currency; unique index on execution_venue_id/metal_id/currency_id/unit_id.
- instrument_mappings: maps reference instruments to execution instruments and required FX/unit conversion assumptions; indexes on reference_market_instrument_id and execution_instrument_id.
- price_quotes: append-only executable bank quotes; indexes on bank_instrument_id/observed_at and fetched_at; retain raw quotes long-term or archive by age.
- market_bars: aggregated bars for reference or execution instruments; unique index on instrument_type/instrument_id/timeframe/bar_start_at; retain long-term for backtests.
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
- execution_premium_snapshots: records converted reference price versus account-bound bank buy/sell prices; indexes on reference_market_instrument_id, execution_instrument_id, captured_at.
- cost_rules: cost rule families by venue/instrument; indexes on execution_venue_id and status.
- cost_rule_versions: date-effective spread, commission, tax, slippage, rounding, and conversion-cost rules; indexes on cost_rule_id/effective_from.
- backtest_dataset_snapshots: immutable dataset identities for reproducible backtests; indexes on instrument, source, start_at, end_at, data_hash.
- system_health_events: collector, scheduler, API, and worker health; indexes on component, status, created_at; archive older noisy data.

## 5. Service Architecture

- BankPriceProvider: fetches public bank quotes; input bank instrument; output PriceQuote candidate; must not persist or trade; test parser, stale data, and failure modes.
- KuveytTurkPriceProvider: first provider implementation; input Kuveyt Turk silver instrument; output bank buy/sell quote; must not bypass login/captcha/private endpoints; test with fixtures.
- FXRateProvider: fetches FX context; output currency pair quote; must not decide trades; test stale/missing data.
- HistoricalMarketDataProvider: fetches historical bars; output normalized bars; must not mix provider data without provenance.
- PriceCollector: schedules providers and persists quotes; must not create signals.
- DataQualityService: validates freshness, duplicates, impossible values, source divergence, and provider failure states before data reaches strategies.
- BarBuilder: converts quotes to bars; must not fetch remote data.
- UnitConversionService: performs all unit conversions with Decimal and configured conversion rules; must not hide ad-hoc conversions inside strategies or brokers.
- CostModelService: calculates detailed date-effective cost breakdowns; must not return only an opaque total.
- IndicatorService: calculates requested indicators and caches snapshots; must not run strategies.
- RegimeDetector: classifies market regime from indicators and bars; must not create orders.
- StrategyEngine: runs enabled strategies and creates TradeIntent; must not execute trades.
- AccountBoundExecutionResolver: resolves a TradeIntent into the account's own execution venue and allowed instrument; must not choose a different bank because its spread is better.
- RiskManager: approves, reduces, or rejects every TradeIntent; must not be bypassed.
- PaperBroker: executes approved paper orders at realistic executable prices; must not call real banks.
- PortfolioService: computes positions and valuations; must not mutate ledger directly except through approved services.
- LedgerService: writes immutable ledger entries; must not edit old entries.
- Clock / RealClock / SimulatedClock: provides time to live and backtest workflows; backtests must not call wall-clock time directly.
- ExecutionPremiumService: records and reports reference-vs-execution premium/discount after explicit FX and unit conversion.
- BacktestDatasetSnapshotService: creates immutable dataset identities so backtest results can be reproduced.
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
Create: src/silverpilot, tests, pyproject.toml.
Acceptance: tests pass; app imports; no trading logic.
Do not include: Docker, DB, bank scraping, Telegram, ML, Hermes.

### Phase 1: Domain model and database schema

Goal: implement first-class domain concepts and PostgreSQL schema.
Deliverables: SQLAlchemy models, Alembic baseline, schema tests.
Acceptance: migration applies locally; relationships and constraints tested.
Do not include: trading strategies.

### Phase 2A: Kuveyt Turk source feasibility spike

Goal: prove whether public Kuveyt Turk silver quotes can be fetched legally, technically, and reliably before provider implementation starts.
Deliverables: the canonical feasibility note in this ROADMAP section covering source URL, format, robots/terms notes, executable-vs-indicative status, timestamp availability, safe fetch frequency, stale states, weekends, holidays, maintenance, and known limitations. Do not create a separate provider markdown file unless Phase 2B needs a narrow parser fixture note.
Acceptance: this roadmap contains explicit source assumptions, and provider implementation is either approved with constraints or blocked with reasons.
Do not include: provider implementation, scraping code, scheduled collectors, other banks.

Feasibility result as of 2026-06-17: conditionally approved for Phase 2B, with constraints.

Official sources inspected:

- Robots: `https://www.kuveytturk.com.tr/robots.txt`
- Silver page: `https://www.kuveytturk.com.tr/kendim-icin/yatirim-urunleri/hazine-urunleri/canli-gumus-fiyatlari-ve-gram-gumus-hesaplama`
- Finance portal page: `https://www.kuveytturk.com.tr/finans-portali`
- Public finance portal endpoint discovery: the official finance portal page currently exposes `addresses["fn-rlrtd"]`, and official `magiclick.core.min.js` exposes `ApiEndpoints.financePortal`.
- Last-known public finance portal JSON path observed from official assets: `/ck0d84?B83A1EF44DD940F2FEC85646BDB25EA0`
- Public parities endpoint discovered from official site JavaScript: `/ck0d84?EB770F761E1233CCE1588AFFCAEBABFC`

Findings:

- `robots.txt` allows `/` and only disallows `/blog/etiket/*`; this is not legal permission by itself, but it does not block the finance/silver pages.
- The official silver page exists and describes live silver prices, digital silver account access, BSMV handling, weekend/night spread widening, and ounce-to-gram conversion.
- The discovered public finance portal endpoint currently returns JSON rows including `GMS (gr)` / `Gümüş` with `BuyRate`, `SellRate`, `ChangeRate`, and `ChangeRateNegative`.
- The public parities endpoint currently returns reference-style rows including `GÜMÜŞ (ONS/$)` with `LastValue`, `Difference`, `Daily`, and `Yearly`.
- The finance portal states that displayed exchange/gold rates are indicative and not binding; transactions use internet or mobile branch rates. Therefore these quotes must be treated as public indicative bank quotes, not guaranteed executable prices.
- The JSON response does not expose a clear provider timestamp. The provider must set `fetched_at`, `observed_at`, and `stored_at`; `provider_reported_at` must remain null unless a reliable source timestamp is later found.
- No official safe polling frequency was found. Phase 2B must start with conservative, bounded polling and explicit rate-limit configuration; no high-frequency or seconds-level polling is allowed.
- Weekend and holiday operation is not a hard closed state: the silver page says mobile/internet branch orders can be placed 7/24, but spreads may widen during weekends, holidays, nights, or international market closures. This must become a risk/freshness/spread rule, not an assumption that the market is always normally tradable.

Phase 2B constraints:

- Implement only the public finance portal JSON path first, discovered from official public Kuveyt Turk assets.
- Do not bypass login, captcha, private banking, mobile-only, or authenticated endpoints.
- Treat `/ck0d84?...` endpoint identifiers as volatile last-known implementation details, not stable source contracts. The provider must discover the current endpoint semantically from `addresses["fn-rlrtd"]` on the finance portal page, then fall back to `ApiEndpoints.financePortal` in official core JavaScript.
- Accept only same-site `/ck0d84?<hash>` endpoint paths. Reject external domains, login/captcha/private/mobile/authenticated paths, and malformed endpoint values.
- Default behavior must fail closed when endpoint discovery, schema, freshness, or field names change. A last-known endpoint path may exist only as diagnostic/configured fallback data, not as the default execution path.
- Parse `GMS (gr)` as the first Kuveyt Turk silver gram/TRY execution quote candidate.
- Store raw provider response hashes for debugging, but do not retain raw payloads long-term in production by default.
- Because quotes are public indicative values, reports must label them as indicative bank quotes until executable parity with internet/mobile branch order screens can be manually verified.
- Phase 2B may proceed only with parser fixtures, data quality checks, stale-data handling, and schema-change failure tests.

### Phase 2B: Kuveyt Turk provider implementation

Goal: implement the first provider only after Phase 2A approves a source-backed path.
Deliverables: provider interface, Kuveyt Turk implementation, endpoint discovery tests, sanitized parser fixtures, freshness checks, parser failure tests.
Acceptance: provider discovers the endpoint through `fn-rlrtd` or `ApiEndpoints.financePortal`, parser detects buy/sell/timestamp when available, fails visibly on bad discovery/schema/freshness fixtures, respects feasibility constraints, and does not bypass login/captcha/private endpoints.
Do not include: other banks, best-bank routing, trading strategies.

### Phase 3: Price storage and bar builder

Goal: persist quotes and aggregate bars.
Deliverables: collector service, quote tables, bar builder.
Acceptance: duplicate handling, freshness, and quote-count bars tested.
Do not include: strategies.

Status as of 2026-06-17: started. `PriceCollector` persists provider quote
candidates into `price_quotes` with service-level duplicate handling, and
`QuoteBarBuilder` creates/upserts execution OHLC bars from persisted quotes.
Remaining Phase 3 work: scheduled collection, broader freshness status
classification, and production retention/archive policy.

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
src/
  silverpilot/
    __init__.py
    app/
      __init__.py
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

Use `src/silverpilot/` as the canonical package layout. Early phases create only the folders they need; future folders are listed here to show intended ownership boundaries, not to encourage empty directory scaffolding.

- src/silverpilot/app/main.py: FastAPI entrypoint.
- src/silverpilot/app/core: settings, logging, common utilities.
- src/silverpilot/app/domain: pure domain models and value objects.
- src/silverpilot/app/db: SQLAlchemy session and persistence helpers.
- src/silverpilot/app/providers: external source interfaces and implementations.
- src/silverpilot/app/collectors: scheduled collection workflows.
- src/silverpilot/app/indicators: indicator calculation and cache logic.
- src/silverpilot/app/regimes: market regime detection.
- src/silverpilot/app/strategies: deterministic strategy implementations.
- src/silverpilot/app/risk: risk policies and decisions.
- src/silverpilot/app/paper_trading: paper orders, executions, positions, ledger integration.
- src/silverpilot/app/portfolio: valuation and snapshots.
- src/silverpilot/app/news: news collection and interpretation.
- src/silverpilot/app/backtesting: historical replay.
- src/silverpilot/app/reporting: PnL, audit, and portfolio reports.
- src/silverpilot/app/api: REST routes and schemas.
- src/silverpilot/app/notifications: Telegram and future adapters.
- tests: unit and integration tests.
- migrations: Alembic revisions, added only when database work begins.
- scripts: small operational scripts only.
- docs: durable design documents only after canonical files exist.

## 23. First Implementation Prompt After Reset

Use this exact prompt next:

```text
Create the clean SilverPilot project skeleton only.
This is Phase 0. Do not implement trading logic.

Requirements:

1. Use one stable package layout:
   - Prefer `src/silverpilot/`
   - Put tests under `tests/`
2. Create `pyproject.toml` for a Python FastAPI project.
3. Add dependencies for:
   - FastAPI
   - Pydantic
   - pytest
   - httpx or FastAPI TestClient support
   - ruff
   - mypy or pyright
4. Create a basic FastAPI app with:
   - `/health`
   - versioned API prefix preparation for `/api/v1`
   - no financial logic in routes
5. Create a settings module with environment-based configuration.
   - Do not read or print secrets.
   - Add `.env.example` with placeholder names only.
   - Ensure `.env` remains ignored.
6. Create only the minimum Phase 0 domain/value models:
   - Money
   - Quantity
   - Currency
   - Metal
   - Unit
   - Bank
   - BankInstrument
   - PriceQuote
   - MarketBar
   - User
   - VirtualAccount
7. These models must:
   - use Decimal for money and quantities
   - avoid float arithmetic
   - include basic validation
   - avoid fake business methods
   - avoid TODO-driven placeholder behavior
   - remain bank-agnostic
   - remain metal-agnostic
8. Add minimal interfaces or placeholders only when needed for type clarity:
   - Clock
   - RealClock
   - SimulatedClock
   - PriceProvider Protocol
   - UnitConversionService Protocol
9. Add tests for:
   - health endpoint
   - Money construction and Decimal behavior
   - Quantity construction and Decimal behavior
   - Currency precision
   - Unit identity
   - BankInstrument construction
   - PriceQuote buy/sell validation
   - MarketBar timestamp validation
   - VirtualAccount account-bound execution context
10. Add code quality setup:
   - ruff check
   - ruff format
   - type checking with mypy or pyright
   - pytest
11. Add GitHub Actions CI for:
   - ruff check
   - ruff format --check
   - type checking
   - pytest
12. Create initial ADR files under `docs/adr/`:
   - ADR-001: paper trading first
   - ADR-002: Python + FastAPI
   - ADR-003: Decimal/numeric for money and quantity
   - ADR-004: Telegram as adapter only
   - ADR-005: account-bound execution, no best-bank routing
13. Run all tests and quality checks.
14. Commit the skeleton with:
   chore: create clean SilverPilot skeleton

Do not implement:
- database models
- Alembic migrations
- Docker
- bank scraping/fetching
- indicators
- strategies
- risk manager
- paper broker
- ledger
- backtest engine
- Telegram
- Hermes
- ML
- dashboard
- multi-bank provider implementations
- real-money trading
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

## 29. Remaining Critical Design Clarifications

These clarifications are mandatory before implementation expands beyond the first skeleton. They prevent ambiguous data, unit, cost, versioning, and API behavior.

### 29.1 Kuveyt Turk Feasibility Before Provider Implementation

Before implementing `KuveytTurkPriceProvider`, create a feasibility spike.

It must answer:

- What is the public source URL?
- Is the source HTML, JSON, RSS, or another format?
- Is scraping/fetching allowed by robots.txt and terms?
- Is the displayed price executable or only indicative?
- Are buy price, sell price, and timestamp available?
- How often can it be fetched safely?
- What happens during maintenance, weekends, holidays, or stale price states?

For this rebuild, the Phase 2A feasibility note is kept in Section 21 of `ROADMAP.md` to avoid markdown sprawl. Provider implementation cannot start until that canonical note conditionally approves Phase 2B.

### 29.2 Reference Market Instrument vs Execution Instrument

Separate reference market data from executable bank pricing.

- `ReferenceMarketInstrument`: signal and indicator data, such as XAGUSD ounce/USD or SI=F.
- `ExecutionInstrument`: executable paper-trading bank quote, such as Kuveyt Turk silver gram/TRY.

Technical indicators may use reference market data if needed, but paper trades must execute only on the execution instrument's realistic bank buy/sell price. Backtest reports must clearly state which instrument was used for signals and which instrument was used for execution.

### 29.3 Unit and Conversion Model

Add explicit unit modeling.

Required concepts:

- `Unit`
- `InstrumentUnit`
- `UnitConversionRule`
- `QuoteUnit`
- `ExecutionUnit`

All conversions must be tested with Decimal. The ounce-to-gram conversion constant must be centralized and covered by deterministic tests. No strategy, provider, broker, risk rule, or report may perform hidden ad hoc unit conversion.

### 29.4 Cost Breakdown Model

The cost model must return detailed components, not only one total cost.

Required components:

- spread cost.
- bank commission.
- tax.
- slippage approximation.
- currency conversion cost.
- rounding adjustment.
- total cost.

Backtest reports must include gross PnL, PnL before costs, PnL after costs, and cost as percentage of gross profit. Cost rules must be versioned and date-effective.

### 29.5 Strategy and Configuration Versioning

Every strategy run and backtest must store:

- strategy name.
- strategy version.
- strategy parameters hash.
- risk policy version.
- cost model version.
- indicator config hash.
- regime detector version.
- code commit SHA if available.
- data snapshot ID.

A backtest is not reproducible unless these fields are persisted.

### 29.6 Backtest Dataset Snapshot

Add `BacktestDatasetSnapshot`.

It must record:

- instrument.
- source.
- start_at.
- end_at.
- quote_count.
- bar_count.
- data_hash.
- filters_applied.
- repair_policy.
- created_at.

Backtests must reference a dataset snapshot.

### 29.7 Clock Abstraction

Add:

- `Clock`
- `RealClock`
- `SimulatedClock`

No backtest code may call wall-clock time directly. Live paper uses `RealClock`. Backtests use `SimulatedClock`.

### 29.8 API Versioning and Remote Safety

All APIs must use versioned paths such as `/api/v1`.

Before any remote-facing mutating endpoint exists, require:

- authentication.
- authorization.
- account ownership checks.
- audit logging.
- rate limiting.
- CORS policy.
- schema tests.

No remote-facing mutating endpoint may exist without auth, ownership check, audit log, and tests.

### 29.9 Database Migration and Backup Discipline

Add:

- migration upgrade tests.
- migration downgrade tests where feasible.
- local dev reset script.
- seed data strategy.
- backup and restore procedure before VPS deployment.

Migration risk must be reviewed before any deploy involving financial state.

### 29.10 Provider Payload and Fixture Policy

Default policy:

- Production should not retain raw provider payloads long-term unless necessary.
- Parser tests may use sanitized fixtures.
- Provider response hash should be stored for debugging.
- No sensitive payload should be committed.

If raw payload retention is introduced, retention, redaction, and access rules must be documented first.

### 29.11 Error Taxonomy

Define typed errors:

- `ProviderUnavailable`
- `ProviderParseError`
- `StaleDataError`
- `DataQualityError`
- `IndicatorInsufficientData`
- `RegimeUncertain`
- `RiskRejected`
- `InsufficientBalance`
- `LedgerInvariantViolation`
- `BacktestDataUnavailable`

Errors must be observable, testable, and mapped consistently to API responses and logs.

### 29.12 Indicator Warmup and Insufficient Data Policy

Indicators must return an explicit insufficient-data state when the warmup window is not satisfied.

- EMA 200 cannot be considered valid with only 50 bars.
- ADX, ATR, and RSI must not produce fake values during warmup.
- RegimeDetector must return NO_TRADE when required indicator inputs are insufficient.

### 29.13 Initial Timeframe and Trading Scope

V1 is not a high-frequency system.

Initial defaults:

- raw quote collection from provider.
- 15m or 1h bars.
- strategy decisions on 1h bars unless changed by config.
- no seconds-level trading.
- no scalping.

V1 trading scope:

- long-only.
- no leverage.
- no margin.
- no short selling.
- no real-money execution.
- cash-based buy.
- position-based sell.

### 29.14 Rounding Policy

Add explicit rounding rules:

- money precision by currency.
- quantity precision by metal/unit.
- bank-specific rounding if observed.
- fee rounding.
- tax rounding.
- portfolio valuation rounding.

No hidden float arithmetic is allowed.

### 29.15 Narrower First Skeleton

Revise the first implementation prompt so Phase 0 creates only the minimum domain/value models:

- `Money`
- `Quantity`
- `Currency`
- `Metal`
- `Unit`
- `Bank`
- `BankInstrument`
- `PriceQuote`
- `MarketBar`
- `User`
- `VirtualAccount`

Do not create all future models in the first skeleton. Add later models in their own phases.

## 30. Multi-Bank, Multi-Metal, Reference-vs-Execution Design

SilverPilot must support multiple banks and multiple precious metals while keeping signal data separate from executable bank pricing.

### 30.1 Multi-Bank Is Mandatory, But Kuveyt Turk Is First

SilverPilot must be designed for multiple banks from day one, even though Kuveyt Turk is implemented first.

- Core trading, paper execution, indicator, regime, risk, and backtest logic must not depend on Kuveyt Turk-specific code.
- Kuveyt Turk is only the first `BankPriceProvider` implementation.
- Future banks such as Ziraat, Is Bankasi, Garanti, Akbank, or others must be added by implementing the same provider interface.
- There must be no `if bank == "kuveyt_turk"` business logic inside core services.
- Bank-specific parsing, source rules, rate limits, freshness rules, field names, and fee rules belong only in provider/config layers.
- The first vertical slice uses Kuveyt Turk only, but the architecture must remain bank-agnostic.

### 30.2 Multi-Metal Is Mandatory

Silver is only the first supported metal.

The domain model must support:

- silver / XAG.
- gold / XAU.
- platinum / XPT.
- palladium / XPD.
- future precious metals if needed.

IndicatorService, StrategyEngine, RiskManager, and PaperBroker must not be silver-specific. Metal-specific behavior must be represented through configuration, instruments, units, and cost rules. The first vertical slice uses silver only, but the architecture must remain metal-agnostic.

### 30.3 Reference Market Instrument vs Execution Instrument

Definitions:

- `Metal`: the underlying precious metal, such as XAG or XAU.
- `ReferenceMarketInstrument`: market data series used for indicators, regimes, and strategy signals, such as XAGUSD, SI=F, XAUUSD, or GC=F.
- `ExecutionInstrument`: instrument used for paper trading execution, such as Kuveyt Turk silver gram/TRY.
- `BankInstrument`: bank-specific execution instrument with buy/sell prices, spread, unit, currency, and cost rules.
- `ExecutionVenue`: place where execution is simulated, initially a bank.

Critical rules:

- Technical indicators and regimes may use `ReferenceMarketInstrument`.
- PaperBroker must execute only on the account-bound `ExecutionInstrument` / `BankInstrument`.
- Reports must show both signal instrument and execution instrument.

Example:

- Signal source: XAGUSD or SI=F.
- Execution source: Kuveyt Turk silver gram/TRY bank buy/sell quote.

### 30.4 V1 Indicator Source Policy

V1 uses a reference-market-first indicator policy.

- Calculate indicators from the selected `ReferenceMarketInstrument`.
- Use bank quotes for execution, spread, cost, risk filters, premium/discount tracking, and portfolio valuation.
- Do not calculate separate strategy indicators for every bank in V1.
- Bank-specific indicator series may be added later only after enough clean bank quote history exists.

Reason:

- Bank quote history may be incomplete, stale, irregular, bank-specific, and affected by spread policy.
- If every bank gets its own indicator series too early, complexity explodes.
- Reference market data gives a cleaner signal baseline.
- Bank prices determine whether a signal is executable after realistic costs in each account.

### 30.5 Bank Premium / Discount Tracking

SilverPilot must track the difference between reference market price and bank executable price.

Add `ExecutionPremiumSnapshot` or an equivalent concept.

It should compare:

- reference converted price.
- bank buy price.
- bank sell price.
- bank spread.
- premium/discount versus reference.
- timestamp and source provenance.

Example conversion:

```text
reference_gram_try = (xagusd_price / ounce_to_gram) * usdtry_price
bank_sell_premium = bank_sell_gram_try - reference_gram_try
bank_buy_discount = reference_gram_try - bank_buy_gram_try
```

This premium/discount must be available to RiskManager and reports.

### 30.6 Account-Bound Execution Resolution

StrategyEngine may produce asset-level TradeIntent, but execution is resolved per virtual account.

Example asset-level intent:

- asset: XAG.
- side: BUY.
- target cash amount: 10000 TRY.
- signal instrument: XAGUSD or SI=F.
- reason: reference trend up + pullback.

For each subscribed account, `AccountBoundExecutionResolver` resolves:

- the account's account-bound execution venue.
- the account's allowed execution instrument for the target metal, unit, and currency.
- the account-bound quote freshness and data quality.
- account/bank-specific spread, fees, taxes, min transaction amount, and risk rules.

The resolver must not choose another bank because its spread is better. Other bank prices are benchmark data only for that account.

### 30.7 Future Bank-Specific Indicator Mode

Bank-specific indicators are allowed only as a future experimental mode.

Requirements before enabling:

- enough clean quote history per bank.
- stable bar construction per bank.
- missing/stale data handling.
- sufficient warmup windows.
- backtest comparison against reference-market indicators.
- report showing whether bank-specific indicators add value after costs.

Default mode remains reference-market indicators for signals and account-bound bank prices for execution.

### 30.8 Signal/Execution Consistency in Backtests

Backtests must store:

- signal instrument.
- signal data source.
- execution instrument.
- execution venue/bank.
- FX conversion source if used.
- unit conversion rule.
- premium/discount snapshots.
- cost model version.

A backtest result is invalid if it mixes reference and execution prices without recording the mapping.

### 30.9 No Hidden Conversions

No strategy, provider, risk rule, broker, or report may perform hidden ad hoc conversions.

All conversions must go through:

- `UnitConversionService`
- `FXRateProvider`
- configured instrument mapping

All conversion assumptions must be visible in reports.

### 30.10 Updated First Vertical Slice

The first vertical slice is:

- Metal: silver / XAG.
- ReferenceMarketInstrument: XAGUSD or SI=F, selected after feasibility check.
- ExecutionVenue: Kuveyt Turk.
- ExecutionInstrument: Kuveyt Turk silver gram/TRY.
- Currency: TRY.
- Bars/timeframe: 15m or 1h, decided by config.
- Strategy: one simple reference-market signal strategy.
- Execution: paper trade at Kuveyt Turk buy/sell prices for the bound account.
- Costs: spread-first, then commission/tax if known and source-backed.
- Reports: PnL before costs, PnL after costs, premium/discount, rejected/no-trade reasons.

Do not add other banks or metals until this vertical slice is stable, tested, and reproducible.

## 31. Account-Bound Execution Correction

SilverPilot must not assume that virtual money can freely move between banks. Each virtual account is bound to its own bank/execution venue. If a user's virtual money is in Kuveyt Turk, the account trades only under Kuveyt Turk pricing, spread, fee, tax, freshness, and availability rules. If another account is in Ziraat, that account trades only under Ziraat rules.

Section 31 supersedes any earlier language that could be interpreted as best-bank routing, dynamic cross-bank execution selection, or automatic movement of funds between banks.

### 31.1 No Cross-Bank Execution Selection

Remove or supersede any design implication that SilverPilot should choose the best bank for a trade based on spread or availability.

Wrong model:

- Strategy says buy XAG.
- System compares Kuveyt Turk, Ziraat, Garanti, and others.
- System chooses the bank with the best spread.
- Trade executes there.

Correct model:

- Strategy says buy XAG.
- Each subscribed virtual account evaluates that signal independently.
- The account's own bank/execution venue determines execution.
- The account may trade only if its own bank quote, spread, fees, taxes, freshness, and risk rules allow it.
- Other banks are not execution candidates for that account.

### 31.2 Account-Bound Execution Layer

Use `AccountBoundExecutionResolver`, not generic best-bank routing.

Responsibilities:

- Read the `VirtualAccount`.
- Determine the account's bound `ExecutionVenue` / `Bank`.
- Determine the allowed `BankInstrument` for the target metal, unit, and currency.
- Fetch or validate the relevant account-bound quote.
- Pass account-bound execution context to RiskManager.
- Create a PaperOrder only for the account's own execution instrument.

It must not:

- choose another bank because its spread is better.
- assume funds can be transferred between banks.
- execute a trade on an instrument not allowed by the account.
- hide bank-specific execution assumptions.

### 31.3 VirtualAccount Must Carry Execution Context

`VirtualAccount` must include or link to:

- user_id.
- base_currency.
- execution_venue_id.
- allowed execution instruments.
- wallets.
- positions.
- account-level strategy subscriptions.
- account-level risk configuration.

A user may have multiple virtual accounts, each bound to a different bank.

Examples:

- Account A: Kuveyt Turk + TRY + silver gram/TRY.
- Account B: Ziraat + TRY + silver gram/TRY.
- Account C: Kuveyt Turk + TRY + gold gram/TRY.

These accounts do not share cash unless an explicit future transfer simulation feature is implemented.

### 31.4 Signal Is Asset-Level, Execution Is Account-Level

StrategyEngine may produce an asset-level TradeIntent.

Example:

- asset: XAG.
- side: BUY.
- target cash amount: 10000 TRY.
- signal instrument: XAGUSD or SI=F.
- reason: reference trend up + pullback.

Then each account resolves execution independently.

For Account A:

- execution venue: Kuveyt Turk.
- execution instrument: Kuveyt Turk silver gram/TRY.
- risk decision: approve/reject/reduce based on Kuveyt Turk rules.

For Account B:

- execution venue: Ziraat.
- execution instrument: Ziraat silver gram/TRY.
- risk decision: approve/reject/reduce based on Ziraat rules.

The system must show when the same signal produced different outcomes across accounts because bank conditions differ.

### 31.5 Other Bank Prices Are Benchmark Data Only

For a given account, other banks' prices may be used only for:

- benchmark reporting.
- spread comparison reports.
- premium/discount analysis.
- market observation.
- future what-if simulations.

They must not be used to execute that account's paper trade. If Account A is bound to Kuveyt Turk, then Ziraat's better spread can be reported as benchmark information, but Account A cannot execute at Ziraat unless a future explicit transfer simulation moves funds to a Ziraat-bound account.

### 31.6 Future Transfer Simulation Is Out of Scope

Simulating money transfer between banks is not part of V1.

Do not implement:

- cross-bank cash movement.
- automatic bank switching.
- best-bank routing.
- transfer fees.
- transfer delays.
- transfer limits.

These may be considered in a future version only after the core paper trading system is stable.

### 31.7 Updated First Vertical Slice

The first vertical slice remains:

- one user.
- one virtual account.
- one bound bank: Kuveyt Turk.
- one execution instrument: Kuveyt Turk silver gram/TRY.
- one reference market instrument: XAGUSD or SI=F.
- one strategy.
- one account-bound paper execution path.

Do not add multi-bank routing. Multi-bank support means multiple independently configured accounts/providers, not dynamic best-bank execution.
