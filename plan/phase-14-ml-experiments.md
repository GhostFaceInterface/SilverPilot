# Phase 14: Offline ML Edge Experiments

Status: PASS.

Phase 14 adds an offline-only ML experiment path for the existing
`trend_up_pullback` BUY candidate universe. It does not change collectors,
strategy execution, risk approval, paper brokerage, Telegram, API behavior,
scheduler behavior, sizing, vetoes, or order generation.

## Implemented Boundary

- Package: `src/silverpilot/app/ml_experiments/`.
- CLI: `silverpilot-ml-experiment`.
- Optional dependency extra: `ml = ["scikit-learn>=1.5.0"]`.
- Metadata tables:
  - `ml_dataset_snapshots`
  - `ml_experiment_runs`
  - `ml_experiment_metrics`
- Artifacts: deterministic `dataset.csv.gz` plus `manifest.json` under
  `mlruns/phase14/<data_hash>/`.

## Data And Labels

The dataset builder reuses `BacktestDatasetSnapshotService` for source-window
identity, then emits row-level artifacts outside the DB. Candidate rows are
created only when the same pure `trend_up_pullback` evaluator would create a
BUY intent.

Feature timestamps must be at or before `decision_at`. Label quotes must be
after `decision_at`. The primary label is `forward_net_return_after_costs`;
`positive_edge` is true only when that value is greater than `min_edge_bps`.
The BUY label uses bank sell price for entry and bank buy price for exit, with
configured fees, taxes, and slippage included.

## Validation

Time-series validation is chronological expanding-window with an embargo. If
there are not enough rows or label classes, the experiment run status is
`insufficient_data` and no fake success metrics are persisted.

Implemented model families are:

- `rule_only`
- `dummy`
- `logistic_regression` when the `ml` extra is installed

Model binaries are not persisted. Promotion to runtime ML remains out of scope
and would require a later ablation gate showing meaningful cost-after-edge
improvement over the rule-only baseline.
