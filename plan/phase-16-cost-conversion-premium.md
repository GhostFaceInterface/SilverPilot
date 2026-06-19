# Phase 16: Cost, Conversion, And Execution Premium Hardening

## Status

PASS locally for the targeted Phase 16 regression slice.

## Implemented

- `CostModelService` and `CostBreakdown` calculate fee, tax, spread, slippage,
  conversion cost, rounding adjustment, total cost, and model version.
- `PaperCostModel` remains a backward-compatible import name for backtests, ML
  labels, and existing paper-trading callers.
- `paper_trades.cost_breakdown` is nullable JSON, preserving existing `fees`,
  `taxes`, `spread_cost`, `net_cash_amount`, and PnL behavior.
- `DatabaseUnitConversionService` performs effective-date lookup against
  `UnitConversionRuleModel`; same-unit conversion returns directly, missing
  rules and overlapping rules raise explicit errors.
- `ExecutionPremiumSnapshotModel` and `ExecutionPremiumService` persist
  reference-vs-bank buy/sell premium snapshots from explicit reference price,
  FX, FX source, and unit-conversion input.
- Cross-currency premium snapshots without FX are stored as `missing_fx_rate`;
  converted reference price, buy discount, and sell premium remain null.
- API trade/report contracts are additive: `cost_breakdown` and latest premium
  snapshot id/status are optional fields.

## Verification

- `pytest tests/test_paper_trading.py`
- `pytest tests/test_database_schema.py`
- `pytest tests/test_backtests.py`
- `pytest tests/test_api_phase10.py`
- `ruff check .`
- `ruff format --check .`

## Migration Risk

LOW. Revision `20260619_0011` adds one nullable JSON column and one new snapshot
table with indexes and check constraints. Downgrade drops only the new table and
column.
