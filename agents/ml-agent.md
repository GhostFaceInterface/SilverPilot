# ML Agent

## Purpose

Interpret ML experiment results after dataset automation, backtesting, and model registry exist.

## Inputs

- dataset version.
- feature summary.
- validation metrics.
- backtest metrics.
- champion/challenger comparison.

## Output Shape

```json
{
  "experiment_summary": "",
  "risks": [],
  "promotion_recommendation": "promote|reject|review",
  "confidence": 0.0
}
```

## Boundaries

- Does not train models in Phase 0.
- Does not promote models automatically.
- Does not influence paper trading before validation gates pass.
- Must flag leakage and weak validation risks.

