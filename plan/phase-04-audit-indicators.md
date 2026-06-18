# Phase 4 Audit: Indicator Service

## ROADMAP Objective

Calculate requested indicators from closed bars and cache snapshots. Start with
EMA, RSI, ATR, ADX, and Bollinger Band Width. Do not calculate every possible
indicator and do not produce regimes, signals, strategy decisions, or orders.

## Current Evidence

- `src/silverpilot/app/indicators/calculators.py` implements EMA, RSI, ATR,
  ADX, and Bollinger Band Width calculations.
- `src/silverpilot/app/indicators/service.py` implements `IndicatorService`,
  parameter hashing, cache upsert, closed-bar lookup, and lookahead rejection.
- `src/silverpilot/app/db/models.py` includes `indicator_snapshots` with a
  unique cache key over instrument, source, timeframe, indicator, parameter
  hash, and source bar end.
- `tests/test_indicators.py` validates deterministic reference fixture values,
  insufficient data failures, all Phase 4 indicators, cache idempotency, closed
  bar lookup, and lookahead rejection.

## Required Interfaces And Schema

- Input: closed `market_bars` for one instrument, source, timeframe, and source
  bar end.
- Output: `indicator_snapshots` with normalized parameters, parameter hash,
  Decimal value, calculated time, and exact source bar end.
- Supported indicator names: `ema`, `rsi`, `atr`, `adx`, `bb_width`.

## Data Flow

The service reads all bars up to the requested source bar end, verifies the
requested bar exists and is closed, normalizes parameters, calculates the
indicator value, then inserts or updates the cache row for the exact source bar
end and parameter hash.

## Failure Modes

- Lookahead calculation where `source_bar_end_at` is after `calculated_at`.
- Calculating against a bar end that is not present.
- Insufficient warmup bars.
- Parameter hash instability.
- Unsupported indicator name.
- Strategy or regime logic leaking into the indicator layer.

## Exact Tests

- `pytest tests/test_indicators.py`
- Assert all supported indicators against deterministic reference values.
- Assert insufficient-data errors.
- Assert cache idempotency.
- Assert unavailable source bar rejection.
- Assert lookahead rejection.

## Done Gate

All supported indicators are deterministic, cached by exact closed-bar window,
reject insufficient or future-looking inputs, and remain pure indicator
calculation without regimes, strategies, orders, or risk decisions.

## Out Of Scope

- Regime detection.
- Strategy intent generation.
- Risk management.
- Broker, ledger, portfolio, backtest.
- Exhaustive indicator catalog.
