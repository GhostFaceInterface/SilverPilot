# Phase 9 Plan: Backtest Engine

## ROADMAP Objective

Answer the core product question over a date range: if an account started with
X virtual money on date A and followed strategy S until date B, what happened?
Deliver deterministic replay engine and report output. Acceptance requires
reproducible PnL, drawdown, rejected trades, and portfolio curve. Do not include
LLM or ML.

## Current Evidence

Phase 9 has not started. It depends on Phase 5 regimes, Phase 6 strategy
intents, Phase 7 risk decisions, Phase 8 broker/ledger behavior, and stored
quotes/bars/indicators from Phase 3-4.

## Required Interfaces And Schema

Add:

- `backtest_dataset_snapshots`: instrument, source, start/end, input ranges,
  data hash, created_at.
- Backtest run/report records as needed for deterministic report output.

Add:

- `SimulatedClock` use throughout replay.
- `BacktestDatasetSnapshotService` to freeze reproducible input identity.
- `BacktestEngine.run(config) -> BacktestReportDTO`.

The engine must reuse strategy, risk, broker, ledger, cost, and portfolio logic
instead of creating a separate optimistic simulator.

## Data Flow

The snapshot service identifies the exact quote, bar, indicator, regime, and
policy inputs for the requested date range and hashes them. The backtest engine
creates an isolated simulated account, advances a simulated clock through the
historical timeline, rebuilds or reads deterministic indicators/regimes, runs
strategy, risk, and paper broker logic, records rejected/no-trade reasons, and
emits portfolio value curve plus final metrics.

## Failure Modes

- Using wall-clock time during replay.
- Mutating live paper accounts.
- Recomputing with drifting input data but reusing the same dataset identity.
- Ignoring rejected intents in the report.
- Reporting PnL before spread, commission, tax, slippage, or conversion costs.
- Implementing separate backtest-only strategy/risk/broker shortcuts.
- Non-deterministic ordering when multiple events share timestamps.

## Exact Tests

- Deterministic replay produces identical output for the same dataset snapshot.
- Dataset hash changes when any input quote/bar/policy changes.
- No wall-clock usage: simulated clock controls all timestamps.
- Cost-inclusive PnL differs from naive price-only PnL.
- Report includes rejected trades and no-trade reasons.
- Portfolio curve includes cash, position value, total value, unrealized PnL,
  realized PnL, and drawdown.
- Backtest uses the same strategy/risk/broker/ledger core as paper trading.
- Live account tables are not mutated by backtest runs.

## Done Gate

Backtests are deterministic, reproducible from stored inputs, cost-inclusive,
audit rejected/no-trade decisions, produce a portfolio curve and drawdown, and
reuse live paper-trading core logic without touching live accounts.

## Out Of Scope

- LLM or ML.
- REST API.
- Telegram or dashboard.
- Real-money execution.
- Multi-bank optimization.
- Hyperparameter search.
