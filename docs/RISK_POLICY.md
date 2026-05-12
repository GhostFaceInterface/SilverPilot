# Risk Policy

This file is the canonical policy for paper-trading safety. Exact thresholds are configured during Phase 4 after real spread and volatility data exists.

## Hard Safety Rules

- Real-money execution is forbidden.
- Bank automation is forbidden.
- Paper trades must go through the risk engine once implemented.
- Missing required data blocks automated paper-trade decisions.
- LLM output cannot override a deterministic block.

## Initial Risk Inputs

- latest buy price.
- latest sell price.
- spread percent.
- 24-hour volatility.
- 7-day volatility.
- cash balance.
- open position size.
- realized daily PnL.
- realized weekly PnL.
- data freshness.
- expected net return after costs.

## Initial Block Reasons

- `SPREAD_TOO_HIGH`
- `VOLATILITY_TOO_HIGH`
- `DAILY_LOSS_LIMIT_REACHED`
- `WEEKLY_LOSS_LIMIT_REACHED`
- `FOMO_RISK`
- `EXPECTED_GAIN_BELOW_COST`
- `STALE_DATA`
- `MISSING_DATA`
- `INSUFFICIENT_CASH`
- `POSITION_LIMIT_REACHED`

## Decision Output

```json
{
  "decision": "blocked",
  "reason_code": "SPREAD_TOO_HIGH",
  "risk_level": "high",
  "confidence": 1.0,
  "details": {}
}
```

Allowed decisions:

- `allow`
- `hold`
- `blocked`

## Phase 4 Validation

- Risk engine cannot be bypassed by the paper-trading engine.
- Every block is persisted with a reason code.
- Every paper trade references a risk decision.
- Stale or missing data blocks action.
- Tests cover spread, loss limit, stale data, and insufficient cash cases.

