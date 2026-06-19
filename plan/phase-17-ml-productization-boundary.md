# Phase 17: Offline ML Productization And Boundary Regressions

## Status

PASS locally for the targeted Phase 17 regression slice.

## Implemented

- ML dataset manifests now include `artifact_schema_version`, config hashes for
  feature, label, split, source, and model-family metadata, plus explicit
  `advisory_only` policy.
- ML dataset invalidation includes feature spec, label spec, split spec, source
  data hash, model-family config, and row payload.
- Experiment reports include advisory-only runtime-boundary metadata and do not
  produce trade intents, sizing, vetoes, approvals, or executions.
- Runtime API, strategy, risk, paper broker, Telegram/notifications, collectors,
  and backtests paths are covered by a static regression proving they do not
  import `ml_experiments`.
- ML artifacts are limited to deterministic dataset/manifest files; tests
  reject model binary suffixes such as `.pkl`, `.joblib`, `.onnx`, `.pt`, and
  `.bin`.
- Default CI remains `.[dev]`; optional logistic-regression smoke requires an
  explicit `.[dev,ml]` environment.

## Verification

- `pytest tests/test_ml_experiments.py`
- `pytest tests/test_backtests.py`
- `ruff check .`
- `ruff format --check .`

## Boundary

Runtime ML remains out of scope. Future promotion must be explicitly approved
and must preserve paper-trading and risk-policy guardrails.
