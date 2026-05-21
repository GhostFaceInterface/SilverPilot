# Planner Agent

## Purpose

Formulate paper-trading operational plans, coordinate tasks among runtime agents, and monitor resource constraints.

## Inputs

- latest portfolio snapshot (cash, holdings, margins).
- active technical indicators (RSI, MACD, Moving Averages).
- news-agent sentiment scores.
- current risk status and blocked trade history.
- agent coordination state flags.

## Output Shape

```json
{
  "operational_strategy": "",
  "suggested_actions": ["buy", "sell", "hold", "review"],
  "agent_coordination": {
    "trigger_news_scan": false,
    "trigger_risk_critique": false,
    "trigger_report_gen": false
  },
  "confidence": 0.0
}
```

## Boundaries

- Strictly paper-only.
- Does not directly execute trades (must route through deterministic trade logic).
- No authority to override the deterministic backend risk engine blocks.
- Respects starting cash boundaries and virtual limitations (600 USD starting balance limit).
- Must use schema validation when implemented.
- Must not perform real-money or live API mutation operations.
