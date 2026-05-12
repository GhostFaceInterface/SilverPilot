# Risk Agent

## Purpose

Explain and critique risk decisions after deterministic risk rules exist.

## Inputs

- risk decision.
- triggering rule codes.
- latest portfolio snapshot.
- latest price snapshot.
- recent blocked actions.

## Output Shape

```json
{
  "risk_summary": "",
  "main_blockers": [],
  "recommended_review_points": [],
  "confidence": 0.0
}
```

## Boundaries

- Does not override the backend risk engine.
- Does not execute trades.
- Does not create real-money workflows.
- Must use schema validation when implemented.
- Strong model usage should be rare and justified.

