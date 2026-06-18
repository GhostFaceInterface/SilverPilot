# Phase 9 Plan: Backtest Engine

## ROADMAP Objective

Answer the core product question over a date range: if an account started with
X virtual money on date A and followed strategy S until date B, what happened?
Deliver deterministic replay engine and report output. Acceptance requires
reproducible PnL, drawdown, rejected trades, and portfolio curve. Do not include
LLM or ML.

## Current Evidence

Phase 9 is implemented in the backend service layer. Evidence:

- `src/silverpilot/app/backtests/service.py`: `BacktestDatasetSnapshotService`,
  `BacktestEngine`, `BacktestConfig`, `BacktestReportDTO`, rejected/no-trade
  DTOs, and portfolio curve DTOs.
- `src/silverpilot/app/db/models.py`: `BacktestDatasetSnapshotModel` and
  `BacktestRunModel`.
- `migrations/versions/20260618_0008_backtest_engine.py`: schema migration for
  dataset snapshots and backtest runs.
- `tests/test_backtests.py`: deterministic replay, dataset hash drift,
  cost-inclusive PnL, rejected/no-trade report entries, shared execution table
  usage, and live-account non-mutation tests.
- `tests/test_database_schema.py` and `tests/test_domain_models.py`: schema and
  domain validation coverage.

## Required Interfaces And Schema

Added:

- `backtest_dataset_snapshots`: instrument, source, start/end, input ranges,
  data hash, and created_at.
- `backtest_runs`: dataset snapshot reference, simulated account reference,
  strategy reference, config hash, status, timestamps, and report JSON.

Added:

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

- `test_backtest_engine_replays_deterministically_with_cost_inclusive_report`
  covers deterministic replay, cost-inclusive PnL, no-trade reasons, drawdown,
  portfolio curve, and live wallet non-mutation.
- `test_backtest_dataset_hash_changes_when_quote_input_changes` covers dataset
  hash drift when input quote data changes.
- `test_backtest_report_includes_rejected_trades_without_live_account_mutation`
  covers rejected risk decisions in the report and live wallet non-mutation.
- `test_backtest_persists_run_report_and_uses_shared_execution_tables` proves
  strategy runs, intents, risk decisions, paper orders, paper trades, and ledger
  entries are produced by the shared core.
- `test_backtest_schema_contains_dataset_and_report_tables`,
  `test_backtest_dataset_hash_is_unique`, and
  `test_backtest_domain_models_validation` cover schema/domain shape.

## Done Gate

PASS. Backtests are deterministic, reproducible from stored inputs,
cost-inclusive, audit rejected/no-trade decisions, produce a portfolio curve and
drawdown, and reuse live paper-trading core logic without touching live
accounts.

## Out Of Scope

- LLM or ML.
- REST API.
- Telegram or dashboard.
- Real-money execution.
- Multi-bank optimization.
- Hyperparameter search.
