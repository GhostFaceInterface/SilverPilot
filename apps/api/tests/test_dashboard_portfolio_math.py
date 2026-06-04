import sys
from decimal import Decimal
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[2] / "dashboard"))

from portfolio_math import live_portfolio_pnl  # noqa: E402


def test_live_portfolio_pnl_uses_current_sell_price_not_snapshot():
    asset_quantity = Decimal("1017.397606")
    average_buy_cost = Decimal("2.457249")
    current_sell_price = Decimal("2.39")
    initial_cash = Decimal("2500.00")
    cash_balance = initial_cash - (asset_quantity * average_buy_cost)

    pnl = live_portfolio_pnl(
        portfolio={"initial_cash": str(initial_cash), "cash_balance": str(cash_balance)},
        snapshot={"realized_pnl": "-5.04", "unrealized_pnl": "-5.04"},
        position={"asset_quantity": str(asset_quantity), "average_buy_cost": str(average_buy_cost)},
        price={"sell_price": str(current_sell_price)},
    )

    expected_unrealized = asset_quantity * (current_sell_price - average_buy_cost)
    expected_net = cash_balance + (asset_quantity * current_sell_price) - initial_cash

    assert pnl["unrealized_pnl"] == expected_unrealized
    assert pnl["net_pnl"] == expected_net
    assert pnl["unrealized_pnl"] != Decimal("-5.04")
