# Risk Policy

This file is the canonical policy for paper-trading safety. Phase 4 has started with deterministic paper-trade risk decisions. Volatility, realized-loss, FOMO, and optional expected-gain blocks are configurable MVP safeguards and can be tuned after runtime data accumulates.

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
- `RISK_CHECK_PASSED`
- `HOLD_REQUESTED`
- `BLOCKED_REQUESTED`

## Data Quality Policy

- Selector/parser failure blocks fresh decisions and marks the source stale.
- Last successful prices may be displayed as stale context, but must not be treated as a fresh decision input.
- Execution-critical bank silver buy/sell, global XAG/USD, and USD/TRY are required before Phase 4 risk decisions can emit trade signals.
- Collector health `blocked` means at least one execution-critical source is missing; automated paper-trade signals must not proceed.
- Collector health `stale` means at least one execution-critical source exists but is too old; automated paper-trade signals must not proceed.
- Fresh manual bank or global XAG fallback may unblock simulation, but it must be treated as degraded and explicitly manual.
- Stooq failure is not a blocker by itself when an approved global XAG/USD fallback is fresh; the failure remains a degraded source-reliability fact.
- Official free sources rank above third-party public pages.
- Paid market-data API sources are disabled during MVP and cannot be required for a risk decision.
- Tax/BSMV rules stay configurable and are not legal or tax advice.
- FRED macro data is context, not an execution trigger by itself.
- Direct BLS is backlog; missing direct BLS data must not block MVP decisions if FRED macro series are available.
- Türkiye data can influence execution-risk scoring because local bank prices, TRY conversion, spread, and local tax/rule context affect simulated fills.
- Türkiye macro data must not be treated as proof of global XAG/USD direction.

## Implemented Phase 4.1 Rules

- `POST /paper-trades` must create a persisted `risk_decisions` row for every persisted paper-trade record.
- Buy/sell requests are blocked when execution-critical bank silver, global XAG/USD, or USD/TRY is missing or stale.
- Buy/sell requests are blocked when request spread exceeds `RISK_MAX_SPREAD_PERCENT`, default `5.0`.
- Buy requests are blocked when required paper cash exceeds the portfolio cash balance.
- Sell requests are blocked when requested quantity exceeds the paper position.
- Policy-blocked buy/sell requests create `paper_trades.action=blocked`, attach `risk_decision_id`, and do not mutate paper balances.
- Hold and user-blocked audit records receive deterministic risk decisions but do not require fresh market data.

## Implemented Phase 4.2 Rules

- Buy/sell requests are blocked when global XAG/USD 24-hour range exceeds `RISK_MAX_24H_VOLATILITY_PERCENT`, default `12.0`.
- Buy/sell requests are blocked when global XAG/USD 7-day range exceeds `RISK_MAX_7D_VOLATILITY_PERCENT`, default `25.0`.
- Buy requests are blocked with `FOMO_RISK` when global XAG/USD rises more than `RISK_FOMO_RISE_PERCENT`, default `6.0`, over `RISK_FOMO_LOOKBACK_MINUTES`, default `180`.
- Buy/sell requests are blocked when realized paper loss reaches `RISK_MAX_DAILY_LOSS_USD`, default `30.0`, or `RISK_MAX_WEEKLY_LOSS_USD`, default `60.0`.
- Paper-buy requests with `expected_exit_price` are blocked with `EXPECTED_GAIN_BELOW_COST` when expected net gain does not exceed `RISK_MIN_EXPECTED_NET_GAIN_PERCENT`, default `0.0`.

## Impact Classification

- Execution-critical: bank silver buy/sell, global XAG/USD, spread, TCMB/USDTRY or bank FX effect, tax/KMV/BSMV.
- Global-market context: U.S. rates, broad USD strength, CPI/PPI, Fed RSS.
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
- Tests cover spread, stale data, missing data, insufficient cash, volatility, realized-loss limits, FOMO, expected-gain checks, and risk-decision references.
