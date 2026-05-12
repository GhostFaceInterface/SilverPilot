# News Agent

## Purpose

Classify silver-related market, macro, and news items after LLM infrastructure exists.

## Inputs

- news title.
- news body or excerpt.
- source URL or source name.
- publication time.
- related asset, if known.

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
- Does not bypass risk policy.
- Must use schema validation when implemented.
- Must record trace metadata when LLM tracing exists.

