# Phase 8 Plan: Paper Broker And Ledger

## ROADMAP Objective

Execute approved orders realistically and account for them. Deliver paper
orders, trades, positions, and immutable ledger entries. Acceptance requires
that buying and selling at the same quote loses money after spread and costs.
Do not include real trading.

## Current Evidence

Phase 8 is implemented in the backend service layer.

- `src/silverpilot/app/paper_trading/service.py` adds `PaperBroker`,
  `PaperOrderRequest`, `PaperCostModel`, and append-only `LedgerService`.
- `src/silverpilot/app/db/models.py` adds `PaperOrderModel`,
  `PaperTradeModel`, `PositionModel`, and `LedgerEntryModel`.
- `migrations/versions/20260618_0007_paper_trading_ledger.py` adds the Phase 8
  tables, indexes, constraints, and downgrade path.
- `tests/test_paper_trading.py` covers buy, sell, same-quote loss,
  idempotency, risk approval refusal, insufficient cash/position refusal, and
  append-only ledger behavior.
- `tests/test_database_schema.py` verifies schema presence and one order per
  risk decision.

## Required Interfaces And Schema

Added:

- `paper_orders`: account, intent, risk decision, side, requested quantity,
  approved quantity, status, created_at.
- `paper_trades`: order, side, quantity, execution price, fees, taxes,
  spread cost, executed_at.
- `positions`: account, bank instrument, quantity, average cost, realized PnL.
- `ledger_entries`: immutable account journal entries with currency, amount,
  entry type, reference type/id, and created_at.

Added:

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

Approved paper orders execute through the broker session transaction, ledger and
positions balance, same-quote round trips lose money after spread/costs, and no
real bank or real-money execution path exists.

## Out Of Scope

- Real trading or bank automation.
- Multi-bank execution routing.
- Advanced order types.
- API endpoints.
- Backtest replay.
- Telegram or dashboard.
