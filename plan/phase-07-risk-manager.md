# Phase 7 Plan: Risk Manager

## ROADMAP Objective

Every trade intent is approved, reduced, or rejected. Deliver risk rules and
persisted decisions. Test stale data, spread, drawdown, and max-size rejections.
Do not include bypass paths.

## Current Evidence

Phase 7 is implemented as of 2026-06-18.

Evidence:

- `src/silverpilot/app/risks/service.py` adds `RiskPolicy`, `RiskContext`, and
  `RiskManager`.
- `src/silverpilot/app/db/models.py` includes `risk_decisions`.
- `migrations/versions/20260618_0005_risk_decisions.py` adds the persisted
  decision table with downgrade support.
- `tests/test_risks.py` covers approve, reduce, stale quote, spread,
  insufficient balance, drawdown, missing context, idempotency, and
  no-execution-state boundaries.
- `tests/test_database_schema.py` validates the table and unique policy
  decision key.
- `tests/test_domain_models.py` validates the `RiskDecision` domain shape.

## Required Interfaces And Schema

Implemented `risk_decisions`:

- `trade_intent_id`
- `decision`: approve, reduce, reject
- `approved_quantity` or approved cash amount
- `policy_version`
- `reasons`
- `constraints_applied`
- `created_at`

Implemented a versioned risk policy DTO with:

- max position size
- max order size
- max daily loss
- max drawdown
- minimum data freshness
- maximum spread threshold
- source divergence rule
- cooldown/no-trade windows
- minimum expected edge after costs

Implemented `RiskManager.evaluate(trade_intent_id, context) ->
RiskDecisionResult`.

## Data Flow

For each `TradeIntent`, the risk manager loads the latest matching
`PriceQuote`, the account base-currency `Wallet`, explicit position exposure,
drawdown, daily-loss, cooldown/no-trade, source-divergence, and expected-edge
inputs. It persists exactly one decision per intent and policy version and
returns approve, reduce, or reject with explicit reasons.

## Failure Modes

- Any path from intent to order that skips RiskManager.
- Approving stale quotes or stale regime/indicator data.
- Ignoring bank spread when estimating affordability or edge.
- Approving sizes above account, policy, or instrument limits.
- Accepting missing drawdown or balance inputs as safe.
- Mutating wallet, order, trade, position, or ledger state.
- Persisting decisions without policy version and reasons.

## Exact Tests

- Approves valid intent within balance, spread, freshness, position, and
  drawdown limits.
- Reduces intent when requested size exceeds max order or position policy but a
  smaller valid size exists.
- Rejects stale quote.
- Rejects spread above threshold.
- Rejects insufficient balance.
- Rejects max drawdown breach from explicit drawdown input.
- Rejects missing required risk context.
- Persists policy version, reasons, and constraints applied.
- Asserts no Phase 8 execution tables are created in Phase 7.
- PaperBroker refusal without an approving RiskDecision remains a Phase 8
  acceptance test.

## Done Gate

Met for the Phase 7 slice: risk decisions are persisted, explainable,
policy-versioned, and idempotent per intent/policy version. No order, trade,
position, or ledger state is created.

## Out Of Scope

- Paper order execution.
- Ledger mutation.
- Real trading.
- Complex portfolio optimization.
- ML risk scoring.
- API endpoints.
