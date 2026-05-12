# News Agent

## Purpose

Classify silver-related market, macro, and news items after LLM infrastructure exists.

## Output Shape

```json
{
  "impact": "positive|negative|neutral|unknown",
  "asset": "silver",
  "confidence": 0.0,
  "summary": "",
  "source_type": "news|macro|market"
}
```

## Boundaries

- Does not execute trades.
- Does not decide portfolio actions.
- Must use schema validation when implemented.

