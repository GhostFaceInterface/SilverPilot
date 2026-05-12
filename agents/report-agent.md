# Report Agent

## Purpose

Generate daily and weekly structured summaries after data, risk, and paper-trading records exist.

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
- Must cite internal records when implemented.

