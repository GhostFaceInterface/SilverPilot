# Report Agent

## Purpose

Generate daily and weekly structured summaries after data, risk, and paper-trading records exist.

## Inputs

- portfolio snapshots.
- paper trades.
- blocked decisions.
- collector health.
- agent runs.

## Output Shape

```json
{
  "portfolio_summary": "",
  "risk_summary": "",
  "actions_taken": [],
  "actions_blocked": [],
  "next_watch_points": []
}
```

## Boundaries

- Summarizes system state.
- Does not decide trades.
- Does not invent missing records.
- Must cite internal records when implemented.
- Must use schema validation when implemented.

