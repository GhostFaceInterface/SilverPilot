from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, PaperTrade, Portfolio, PortfolioSnapshot
from app.schemas.paper_trading import PaperTradeRequest

MONEY_QUANT = Decimal("0.000001")


class PaperTradingError(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    quantity: Decimal
    buy_quantity: Decimal
    buy_net_amount: Decimal
    sell_quantity: Decimal
    sell_net_amount: Decimal

    @property
    def average_buy_cost(self) -> Decimal:
        if self.buy_quantity <= 0:
            return Decimal("0")
        return (self.buy_net_amount / self.buy_quantity).quantize(MONEY_QUANT)


def execute_paper_trade(db: Session, request: PaperTradeRequest) -> tuple[PaperTrade, PortfolioSnapshot]:
    portfolio = _get_portfolio(db, request.portfolio_name)
    if portfolio.is_real_money:
        raise PaperTradingError("Real-money portfolios are not allowed in SilverPilot")

    asset = _get_asset(db, request.asset_symbol)
    current_position = calculate_position(db, portfolio.id, asset.id)

    quantity, price, gross_amount, net_amount = _calculate_trade_amounts(request)
    if request.action == "paper_buy" and portfolio.cash_balance < net_amount:
        raise PaperTradingError("Insufficient paper cash balance")
    if request.action == "paper_sell" and current_position.quantity < quantity:
        raise PaperTradingError("Insufficient paper asset quantity")

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action=request.action,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        fees=request.fees,
        taxes=request.taxes,
        net_amount=net_amount,
    )
    db.add(trade)

    if request.action == "paper_buy":
        portfolio.cash_balance = _money(portfolio.cash_balance - net_amount)
    elif request.action == "paper_sell":
        portfolio.cash_balance = _money(portfolio.cash_balance + net_amount)

    db.flush()

    snapshot = create_portfolio_snapshot(
        db=db,
        portfolio=portfolio,
        asset_id=asset.id,
        mark_price=request.sell_price,
    )
    db.commit()
    db.refresh(trade)
    db.refresh(snapshot)
    return trade, snapshot


def create_portfolio_snapshot(
    db: Session,
    portfolio: Portfolio,
    asset_id: int,
    mark_price: Decimal,
) -> PortfolioSnapshot:
    position = calculate_position(db, portfolio.id, asset_id)
    liquidation_value = _money(position.quantity * mark_price)
    portfolio_value = _money(portfolio.cash_balance + liquidation_value)
    realized_pnl = _money(position.sell_net_amount - (position.average_buy_cost * position.sell_quantity))
    unrealized_pnl = _money(liquidation_value - (position.average_buy_cost * position.quantity))

    snapshot = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        cash_balance=portfolio.cash_balance,
        asset_quantity=position.quantity,
        portfolio_value=portfolio_value,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        observed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def calculate_position(db: Session, portfolio_id: int, asset_id: int) -> Position:
    trades = db.execute(
        select(PaperTrade).where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.asset_id == asset_id,
            PaperTrade.action.in_(("paper_buy", "paper_sell")),
        )
    ).scalars()

    buy_quantity = Decimal("0")
    buy_net_amount = Decimal("0")
    sell_quantity = Decimal("0")
    sell_net_amount = Decimal("0")
    for trade in trades:
        if trade.action == "paper_buy":
            buy_quantity += trade.quantity
            buy_net_amount += trade.net_amount
        elif trade.action == "paper_sell":
            sell_quantity += trade.quantity
            sell_net_amount += trade.net_amount

    return Position(
        quantity=_money(buy_quantity - sell_quantity),
        buy_quantity=_money(buy_quantity),
        buy_net_amount=_money(buy_net_amount),
        sell_quantity=_money(sell_quantity),
        sell_net_amount=_money(sell_net_amount),
    )


def _calculate_trade_amounts(request: PaperTradeRequest) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if request.action == "paper_buy":
        price = request.buy_price
        quantity = request.quantity
        if quantity is None:
            spendable = request.cash_amount - request.fees - request.taxes
            if spendable <= 0:
                raise PaperTradingError("cash_amount must exceed fees and taxes")
            quantity = (spendable / price).quantize(MONEY_QUANT, rounding=ROUND_DOWN)
        if quantity <= 0:
            raise PaperTradingError("paper_buy quantity must be greater than zero")
        gross_amount = _money(quantity * price)
        net_amount = _money(gross_amount + request.fees + request.taxes)
        return quantity, price, gross_amount, net_amount

    if request.action == "paper_sell":
        quantity = request.quantity or Decimal("0")
        price = request.sell_price
        gross_amount = _money(quantity * price)
        net_amount = _money(gross_amount - request.fees - request.taxes)
        if net_amount < 0:
            raise PaperTradingError("fees and taxes cannot exceed paper sell proceeds")
        return quantity, price, gross_amount, net_amount

    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")


def _get_portfolio(db: Session, name: str) -> Portfolio:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == name)).scalar_one_or_none()
    if portfolio is None:
        raise PaperTradingError(f"Portfolio not found: {name}")
    return portfolio


def _get_asset(db: Session, symbol: str) -> Asset:
    asset = db.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
    if asset is None:
        raise PaperTradingError(f"Asset not found: {symbol}")
    return asset


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)
