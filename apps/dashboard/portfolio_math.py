from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def live_portfolio_pnl(
    *,
    portfolio: dict[str, Any],
    snapshot: dict[str, Any],
    position: dict[str, Any],
    price: dict[str, Any],
) -> dict[str, Decimal | None]:
    asset_quantity = decimal_value(position.get("asset_quantity"))
    average_buy_cost = decimal_value(position.get("average_buy_cost"))
    current_sell_price = decimal_value(price.get("sell_price"))
    realized_pnl = decimal_value(snapshot.get("realized_pnl"))

    unrealized_pnl = None
    if asset_quantity is not None and average_buy_cost is not None and current_sell_price is not None:
        unrealized_pnl = asset_quantity * (current_sell_price - average_buy_cost)

    cash_balance = decimal_value(portfolio.get("cash_balance")) or decimal_value(position.get("cash_balance"))
    initial_cash = decimal_value(portfolio.get("initial_cash"))

    net_pnl = None
    if (
        cash_balance is not None
        and asset_quantity is not None
        and current_sell_price is not None
        and initial_cash is not None
    ):
        net_pnl = cash_balance + (asset_quantity * current_sell_price) - initial_cash
    elif realized_pnl is not None and unrealized_pnl is not None:
        net_pnl = realized_pnl + unrealized_pnl

    return {
        "net_pnl": net_pnl,
        "unrealized_pnl": unrealized_pnl,
    }
