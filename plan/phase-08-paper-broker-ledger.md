# Phase 8 Plan: Paper Broker And Ledger

## ROADMAP Objective

Execute approved orders realistically and account for them. Deliver paper
orders, trades, positions, and immutable ledger entries. Acceptance requires
that buying and selling at the same quote loses money after spread and costs.
Do not include real trading.

## Current Evidence

Phase 8 has not started. It depends on Phase 7 approving risk decisions, Phase 3
quotes, and Phase 1 account, wallet, and instrument schema.

## Required Interfaces And Schema

Add:

- `paper_orders`: account, intent, risk decision, side, requested quantity,
  approved quantity, status, created_at.
- `paper_trades`: order, side, quantity, execution price, fees, taxes,
  spread cost, executed_at.
- `positions`: account, bank instrument, quantity, average cost, realized PnL.
- `ledger_entries`: immutable account journal entries with currency, amount,
  entry type, reference type/id, and created_at.

Add:

- `PaperBroker.execute(order, quote) -> PaperTradeDTO`
- `LedgerService.append(entries)`, append-only only.

Buying uses the bank sell price. Selling uses the bank buy price.

## Data Flow

An approved risk decision becomes a paper order. The broker validates idempotency
and account/instrument eligibility, prices the order using the current bank
quote and cost model, writes trade, position update, wallet update, and ledger
entries inside one transaction, then marks the order executed. Repeated
execution of the same order returns the existing result or fails without double
posting.

## Failure Modes

- Executing an order without approved RiskDecision.
- Using bank buy price for buys or bank sell price for sells.
- Double execution of the same order.
- Negative cash balance or negative position.
- Ledger entries updated in place after creation.
- Partial transaction writes that leave trade without ledger or position state.
- Ignoring fees, taxes, spread cost, rounding, or precision rules.

## Exact Tests

- Buy creates order, trade, reduced cash wallet, increased position, and ledger
  entries.
- Sell reduces position, increases cash wallet, realizes PnL, and writes ledger
  entries.
- Buy then sell at the same quote loses money after spread and configured costs.
- Broker rejects orders without approving RiskDecision.
- Broker rejects insufficient cash and insufficient position.
- Re-executing the same order does not duplicate trade or ledger entries.
- Ledger entries are append-only and never updated in place.
- Transaction rollback leaves no partial state on failure.

## Done Gate

Approved paper orders execute through one broker transaction, ledger and
positions balance, same-quote round trips lose money after spread/costs, and no
real bank or real-money execution path exists.

## Out Of Scope

- Real trading or bank automation.
- Multi-bank execution routing.
- Advanced order types.
- API endpoints.
- Backtest replay.
- Telegram or dashboard.
