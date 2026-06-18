# Phase 5 Plan: Rule-Based Regime Detector

## ROADMAP Objective

Classify regimes using indicators and hysteresis. Deliver a regime service and
persisted snapshots. Test trend, range, high-volatility, low-volatility, and
no-trade cases. Do not include an ML classifier.

## Current Evidence

Phase 5 is implemented as of 2026-06-18.

- `src/silverpilot/app/regimes/service.py` implements `RegimeDetector`,
  `RegimeDetectorConfig`, candidate classification, stale/missing data
  NO_TRADE behavior, hysteresis, cooldown, and idempotent snapshot upsert.
- `src/silverpilot/app/db/models.py` includes `market_regime_snapshots`.
- `migrations/versions/20260618_0003_market_regime_snapshots.py` adds the
  schema with downgrade support.
- `src/silverpilot/app/domain/models.py` includes `MarketRegimeSnapshot`.
- `tests/test_regimes.py` covers regime classification, NO_TRADE,
  hysteresis, cooldown, idempotency, and lookahead rejection.

## Required Interfaces And Schema

Add a domain shape equivalent to `MarketRegime`:

- `instrument_type`, `instrument_id`, `source`, `timeframe`
- `regime`: `TREND_UP`, `TREND_DOWN`, `RANGE`, `HIGH_VOLATILITY`,
  `LOW_VOLATILITY`, or `NO_TRADE`
- `confidence`: Decimal or bounded numeric value from 0 to 1
- `evidence`: JSON with indicator values, thresholds, freshness, and reasons
- `starts_at`, `confirmed_at`, `source_bar_end_at`

Add `market_regime_snapshots` with indexes on instrument, timeframe,
`confirmed_at`, and `regime`. Add a uniqueness rule that prevents duplicate
snapshots for the same instrument/source/timeframe/source bar end/config
version.

Add `RegimeDetector.detect(context) -> MarketRegimeDTO` or the local equivalent.
The detector must not create intents, orders, trades, or risk decisions.

## Data Flow

The detector reads the required indicator snapshots and the latest closed bars
for one instrument/timeframe. It evaluates rule candidates, applies hysteresis
and cooldown against recent regime snapshots, emits `NO_TRADE` when data is
stale or insufficient, and persists a snapshot containing confidence and
evidence JSON.

## Failure Modes

- Switching regime on a single candle without N confirmations.
- Ignoring cooldown after a regime change.
- Using stale or missing indicators as tradable regimes.
- Looking ahead beyond the requested source bar end.
- Producing strategy intents or orders from the regime layer.
- Hiding thresholds outside a versioned config.
- Creating duplicate snapshots for the same evaluation window.

## Exact Tests

- TREND_UP from EMA50 above EMA200, positive slope, and ADX confirmation.
- TREND_DOWN from EMA50 below EMA200, negative slope, and ADX confirmation.
- RANGE from weak ADX and bounded Bollinger Band Width.
- HIGH_VOLATILITY from ATR expansion and/or high Bollinger Band Width.
- LOW_VOLATILITY from compressed ATR and Bollinger Band Width.
- NO_TRADE for stale indicators, missing warmup, missing bars, or bad source
  quality.
- Hysteresis requires N consecutive confirmations before switching.
- Cooldown preserves the prior regime or emits NO_TRADE during the configured
  window.
- Snapshot cache is idempotent for the same source bar end and config version.
- Lookahead rejection when requested indicator or bar data is after evaluation
  time.

## Done Gate

PASS. `RegimeDetector` persists explainable snapshots, handles stale and
insufficient data as `NO_TRADE`, passes all regime transition tests, and has no
strategy, risk, broker, ledger, backtest, ML, or API behavior.

## Out Of Scope

- ML regime classifier.
- Strategy selection.
- Trade intents.
- Risk decisions.
- Paper execution.
- REST API.
- Telegram, Hermes, dashboard.
