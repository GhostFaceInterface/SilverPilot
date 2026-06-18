# Phase 6 Plan: One Simple Strategy

## ROADMAP Objective

Produce `TradeIntent` from one strategy. Deliver a strategy engine and one
trend-up pullback strategy. Test intent generation and no-intent cases. Do not
include direct execution.

## Current Evidence

Phase 6 has not started. It depends on Phase 5 regime snapshots and Phase 4
indicator snapshots.

## Required Interfaces And Schema

Add:

- `strategies`: name, version, parameters, enabled, created_at, updated_at.
- `strategy_runs`: strategy id, account id, instrument, source bar end, run time,
  regime snapshot id, input hash, status, evidence JSON.
- `trade_intents`: account id, strategy run id, side, quantity or cash amount,
  signal time, status, rationale, evidence JSON.

Add service contracts:

- `Strategy.evaluate(context) -> list[TradeIntentDTO]`
- `StrategyEngine.run(account, strategy, context) -> StrategyRunResult`

Trade intents are proposals only. They must not mutate balances, positions,
orders, trades, or ledger entries.

## Data Flow

The engine loads one enabled trend-up pullback strategy, the latest acceptable
Phase 5 regime snapshot, required indicators, recent bars, account/instrument
eligibility, and a deterministic clock. In `TREND_UP`, the strategy may emit a
long intent when pullback and momentum rules pass. In all other regimes or data
failure states, it records a run and emits no intents.

## Failure Modes

- Strategy creating orders or trades directly.
- Long entry outside `TREND_UP`.
- Emitting intents when regime is `NO_TRADE`, stale, or missing.
- Emitting intents without required indicators.
- Creating short behavior before long-only strategy support is defined.
- Non-deterministic intent sizing or timestamps.
- Missing persisted no-intent rationale.

## Exact Tests

- Generates one long intent for a valid TREND_UP pullback setup.
- Emits no intent when regime is TREND_DOWN, RANGE, HIGH_VOLATILITY,
  LOW_VOLATILITY, or NO_TRADE.
- Emits no intent when EMA, RSI, ATR, or required bar data is missing or stale.
- Verifies long-only behavior: no short intents.
- Persists `strategy_runs` for both intent and no-intent cases.
- Persists rationale/evidence for generated and suppressed signals.
- Asserts no `paper_orders`, `paper_trades`, positions, or ledger entries are
  created by the strategy layer.

## Done Gate

The strategy engine deterministically records runs and emits trade intents only
for the approved trend-up pullback case. No direct execution, risk approval,
broker, ledger, backtest, API, ML, Hermes, or Telegram behavior exists.

## Out Of Scope

- Multiple strategies.
- Configurable strategy selection beyond one enabled strategy.
- Short selling.
- Risk approval.
- Paper execution.
- Portfolio valuation.
- Backtesting.
