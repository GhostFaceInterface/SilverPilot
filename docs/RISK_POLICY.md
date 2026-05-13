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
- source reliability.
- parser status.
- source legal/ToS risk.
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
- `SOURCE_RISK_TOO_HIGH`
- `PARSER_FAILURE`
- `INSUFFICIENT_CASH`
- `POSITION_LIMIT_REACHED`

## Data Quality Policy

- Selector/parser failure blocks fresh decisions and marks the source stale.
- Last successful prices may be displayed as stale context, but must not be treated as a fresh decision input.
- Execution-critical bank silver buy/sell price is required before Phase 4 risk decisions can emit trade signals.
- Collector health `blocked` means no bank silver buy/sell price is available; automated paper-trade signals must not proceed.
- Collector health `stale` means the latest bank price exists but is too old; automated paper-trade signals must not proceed.
- Fresh manual bank-price fallback may unblock simulation, but it must be treated as degraded and explicitly manual.
- Official free sources rank above third-party public pages.
- Paid market-data API sources are disabled during MVP and cannot be required for a risk decision.
- Tax/BSMV rules stay configurable and are not legal or tax advice.
- FRED macro data is context, not an execution trigger by itself.
- Direct BLS is backlog; missing direct BLS data must not block MVP decisions if FRED macro series are available.
- Türkiye data can influence execution-risk scoring because local bank prices, TRY conversion, spread, and local tax/rule context affect simulated fills.
- Türkiye macro data must not be treated as proof of global XAG/USD direction.

## Impact Classification

- Execution-critical: bank silver buy/sell, spread, TCMB/USDTRY or bank FX effect, tax/KMV/BSMV.
- Global-market context: XAG/USD, U.S. rates, broad USD strength, CPI/PPI, Fed RSS.
- Local-macro context: TCMB rates, TRY pressure, Türkiye inflation, local confidence indicators, official rule changes.
- Optional/backlog: direct BLS, TÜİK automated collector, deeper TCMB EVDS series, paid market-data APIs.

## Runtime Memory Role

- The deterministic risk policy remains the decision owner.
- Runtime memory provides historical context only; it cannot override the risk engine.
- Memory records can inform source trust score, stale source warnings, repeated collector failure detection, repeated agent overconfidence warnings, and postmortem-informed warnings.
- Risk decisions may write compact memory events, but raw price/news payloads and full LLM traces must stay out of memory tables.
- If memory lookup returns no relevant records, risk evaluation must still work.

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
