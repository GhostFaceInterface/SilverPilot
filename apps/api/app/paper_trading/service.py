from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, PaperTrade, Portfolio, PortfolioSnapshot, PriceSnapshot, RawFxRate
from app.risk.service import TradeAmounts, evaluate_paper_trade_risk
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
    portfolio = _get_portfolio(db, request.portfolio_name, lock=True)
    if portfolio.is_real_money:
        raise PaperTradingError("Real-money portfolios are not allowed in SilverPilot")

    asset = _get_asset(db, request.asset_symbol)

    # --- Option C: Auto-inject %0.2 BSMV/Kambiyo tax for XAG_GRAM paper buy ---
    if request.action == "paper_buy" and asset.symbol == "XAG_GRAM":
        price = request.buy_price
        if request.quantity is not None:
            gross = request.quantity * price
            request.taxes = _money(gross * Decimal("0.002"))
        elif request.cash_amount is not None:
            spendable = request.cash_amount - request.fees
            gross = spendable / Decimal("1.002")
            request.taxes = _money(gross * Decimal("0.002"))

    current_position = calculate_position(db, portfolio.id, asset.id)

    # FX conversion logic when asset.currency != portfolio.base_currency
    fx_rate = Decimal("1.0")
    if asset.currency != portfolio.base_currency:
        fx_rate = _get_fx_rate(db, portfolio.base_currency, asset.currency)

        # Convert prices and expenses to base currency (USD) so downstream steps
        # (risk checks, database record, snapshot mark price) see USD normalized values.
        request.buy_price = _money(request.buy_price / fx_rate)
        request.sell_price = _money(request.sell_price / fx_rate)
        request.fees = _money(request.fees / fx_rate)
        request.taxes = _money(request.taxes / fx_rate)
        if request.expected_exit_price is not None:
            request.expected_exit_price = _money(request.expected_exit_price / fx_rate)

    quantity, price, gross_amount, net_amount = _calculate_trade_amounts(request, fx_rate=Decimal("1.0"))
    risk_decision = evaluate_paper_trade_risk(
        db,
        request=request,
        portfolio=portfolio,
        asset=asset,
        position=current_position,
        amounts=TradeAmounts(
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            net_amount=net_amount,
        ),
    )
    stored_action = request.action if risk_decision.decision != "blocked" else "blocked"

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action=stored_action,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        fees=request.fees,
        taxes=request.taxes,
        net_amount=net_amount,
        risk_decision_id=risk_decision.id,
    )
    db.add(trade)

    if risk_decision.decision == "allow" and request.action == "paper_buy":
        portfolio.cash_balance = _money(portfolio.cash_balance - net_amount)
    elif risk_decision.decision == "allow" and request.action == "paper_sell":
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
    buy_stats = db.execute(
        select(
            func.sum(PaperTrade.quantity).label("total_qty"),
            func.sum(PaperTrade.net_amount).label("total_net"),
        ).where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.asset_id == asset_id,
            PaperTrade.action == "paper_buy",
        )
    ).one_or_none()

    sell_stats = db.execute(
        select(
            func.sum(PaperTrade.quantity).label("total_qty"),
            func.sum(PaperTrade.net_amount).label("total_net"),
        ).where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.asset_id == asset_id,
            PaperTrade.action == "paper_sell",
        )
    ).one_or_none()

    buy_quantity = buy_stats.total_qty or Decimal("0") if buy_stats else Decimal("0")
    buy_net_amount = buy_stats.total_net or Decimal("0") if buy_stats else Decimal("0")
    sell_quantity = sell_stats.total_qty or Decimal("0") if sell_stats else Decimal("0")
    sell_net_amount = sell_stats.total_net or Decimal("0") if sell_stats else Decimal("0")

    return Position(
        quantity=_money(buy_quantity - sell_quantity),
        buy_quantity=_money(buy_quantity),
        buy_net_amount=_money(buy_net_amount),
        sell_quantity=_money(sell_quantity),
        sell_net_amount=_money(sell_net_amount),
    )


def _get_fx_rate(db: Session, base_currency: str, quote_currency: str) -> Decimal:
    if base_currency == quote_currency:
        return Decimal("1.0")

    # We query the PriceSnapshot table first
    stmt = (
        select(PriceSnapshot)
        .where(
            PriceSnapshot.source.in_(
                [
                    "tcmb-today-xml",
                    "tcmb",
                    "yahoo-usd-try",
                    "yahoo_usd_try",
                    "yahoo-usdtry",
                    "usdtry=x",
                    "usdtry",
                ]
            )
        )
        .order_by(PriceSnapshot.observed_at.desc())
        .limit(1)
    )
    fx_snap = db.execute(stmt).scalar_one_or_none()
    if fx_snap is not None:
        fx_rate = fx_snap.mid_price
    else:
        # Fallback to RawFxRate
        stmt_raw = (
            select(RawFxRate)
            .where(
                RawFxRate.base_currency == base_currency,
                RawFxRate.quote_currency == quote_currency,
            )
            .order_by(RawFxRate.observed_at.desc())
            .limit(1)
        )
        raw_fx = db.execute(stmt_raw).scalar_one_or_none()
        if raw_fx is not None:
            fx_rate = raw_fx.rate
        else:
            raise PaperTradingError(
                f"No valid FX conversion rate found for {base_currency}/{quote_currency} in the database."
            )

    if fx_rate <= 0:
        raise PaperTradingError(f"Invalid FX rate found: {fx_rate}")

    return fx_rate


def _calculate_trade_amounts(
    request: PaperTradeRequest,
    fx_rate: Decimal = Decimal("1.0"),
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    # Normalizes prices, fees, and taxes to portfolio's base currency using fx_rate if applicable
    buy_price = _money(request.buy_price / fx_rate)
    sell_price = _money(request.sell_price / fx_rate)
    fees = _money(request.fees / fx_rate)
    taxes = _money(request.taxes / fx_rate)

    if request.action == "paper_buy":
        price = buy_price
        quantity = request.quantity
        if quantity is None:
            spendable = request.cash_amount - fees - taxes
            if spendable <= 0:
                raise PaperTradingError("cash_amount must exceed fees and taxes")
            quantity = (spendable / price).quantize(MONEY_QUANT, rounding=ROUND_DOWN)
        if quantity <= 0:
            raise PaperTradingError("paper_buy quantity must be greater than zero")
        gross_amount = _money(quantity * price)
        net_amount = _money(gross_amount + fees + taxes)
        return quantity, price, gross_amount, net_amount

    if request.action == "paper_sell":
        quantity = request.quantity or Decimal("0")
        price = sell_price
        gross_amount = _money(quantity * price)
        net_amount = _money(gross_amount - fees - taxes)
        if net_amount < 0:
            raise PaperTradingError("fees and taxes cannot exceed paper sell proceeds")
        return quantity, price, gross_amount, net_amount

    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")


def _get_portfolio(db: Session, name: str, lock: bool = False) -> Portfolio:
    stmt = select(Portfolio).where(Portfolio.name == name)
    if lock and db.bind is not None and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    portfolio = db.execute(stmt).scalar_one_or_none()
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
