# Phase 7 Plan: Risk Manager

## ROADMAP Objective

Every trade intent is approved, reduced, or rejected. Deliver risk rules and
persisted decisions. Test stale data, spread, drawdown, and max-size rejections.
Do not include bypass paths.

## Current Evidence

Phase 7 has not started. It depends on Phase 6 trade intents, Phase 3 quotes,
and account/wallet/instrument schema from Phase 1.

## Required Interfaces And Schema

Add `risk_decisions`:

- `trade_intent_id`
- `decision`: approve, reduce, reject
- `approved_quantity` or approved cash amount
- `policy_version`
- `reasons`
- `constraints_applied`
- `created_at`

Add a versioned risk policy DTO with:

- max position size
- max order size
- max daily loss
- max drawdown
- minimum data freshness
- maximum spread threshold
- source divergence rule
- cooldown/no-trade windows
- minimum expected edge after costs

Add `RiskManager.evaluate(intent, context) -> RiskDecisionDTO`.

## Data Flow

For each `TradeIntent`, the risk manager loads current quote, account wallet,
position exposure, drawdown input, spread, freshness state, regime state, and
policy version. It persists exactly one decision for the evaluated intent and
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
- Asserts PaperBroker refuses orders without an approving RiskDecision in Phase
  8 tests.

## Done Gate

Every intent receives a persisted approve/reduce/reject decision, decisions are
explainable and policy-versioned, and no order execution bypass exists in the
designed flow.

## Out Of Scope

- Paper order execution.
- Ledger mutation.
- Real trading.
- Complex portfolio optimization.
- ML risk scoring.
- API endpoints.
