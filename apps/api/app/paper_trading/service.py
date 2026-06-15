from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Asset,
    PaperTrade,
    Portfolio,
    PortfolioSnapshot,
    PriceSnapshot,
    Provider,
    ProviderCostRule,
    RawFxRate,
    RiskDecision,
    TradeIntentRecord,
)
from app.services.account_ledger import record_paper_trade_ledger_entry
from app.models.entities import TenantPortfolio
from app.risk.service import TradeAmounts, evaluate_paper_trade_risk
from app.schemas.paper_trading import PaperTradeRequest
from app.services.cost_models import COST_MODEL_REGISTRY

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


@dataclass(frozen=True)
class TradeCostBreakdown:
    gross_amount: Decimal
    fees: Decimal
    taxes: Decimal
    spread_impact: Decimal
    net_amount: Decimal
    mid_price: Decimal


@dataclass(frozen=True)
class ProviderCostRuleCosts:
    fees: Decimal
    taxes: Decimal


def execute_paper_trade(db: Session, request: PaperTradeRequest) -> tuple[PaperTrade, PortfolioSnapshot]:
    return _execute_paper_trade(db, request, precomputed_risk_decision=None, trade_intent_record=None)


def execute_paper_trade_with_risk_decision(
    db: Session,
    request: PaperTradeRequest,
    risk_decision: RiskDecision,
    trade_intent_record: TradeIntentRecord | None = None,
) -> tuple[PaperTrade, PortfolioSnapshot]:
    return _execute_paper_trade(
        db, request, precomputed_risk_decision=risk_decision, trade_intent_record=trade_intent_record
    )


def _execute_paper_trade(
    db: Session,
    request: PaperTradeRequest,
    precomputed_risk_decision: RiskDecision | None,
    trade_intent_record: TradeIntentRecord | None,
) -> tuple[PaperTrade, PortfolioSnapshot]:
    portfolio = _get_portfolio(db, request.portfolio_name, lock=True)
    if portfolio.is_real_money:
        raise PaperTradingError("Real-money portfolios are not allowed in SilverPilot")

    asset = _get_asset(db, request.asset_symbol)

    # --- Auto-inject fees and taxes using the active cost model ---
    _inject_provider_costs(db, request=request, portfolio=portfolio, asset=asset)

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
    cost_breakdown = _calculate_cost_breakdown(
        request, quantity=quantity, gross_amount=gross_amount, net_amount=net_amount
    )
    risk_decision = precomputed_risk_decision or evaluate_paper_trade_risk(
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
        trade_intent_id=trade_intent_record.id if trade_intent_record is not None else None,
        action=stored_action,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        fees=request.fees,
        taxes=request.taxes,
        spread_impact=cost_breakdown.spread_impact,
        net_amount=net_amount,
        cost_breakdown_json={
            "gross_amount": str(cost_breakdown.gross_amount),
            "fees": str(cost_breakdown.fees),
            "taxes": str(cost_breakdown.taxes),
            "spread_impact": str(cost_breakdown.spread_impact),
            "net_amount": str(cost_breakdown.net_amount),
            "mid_price": str(cost_breakdown.mid_price),
        },
        risk_decision_id=risk_decision.id,
    )
    db.add(trade)

    if risk_decision.decision == "allow" and request.action in ("paper_buy", "paper_sell"):
        sign = -1 if request.action == "paper_buy" else 1
        portfolio.cash_balance = _money(portfolio.cash_balance + sign * net_amount)

    db.flush()
    if risk_decision.decision == "allow" and request.action in ("paper_buy", "paper_sell"):
        record_paper_trade_ledger_entry(db, portfolio=portfolio, asset=asset, trade=trade)

    snapshot = create_portfolio_snapshot(
        db=db,
        portfolio=portfolio,
        asset_id=asset.id,
        mark_price=request.sell_price,
        price_snapshot_id=_latest_price_snapshot_id(db, asset.id),
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
    price_snapshot_id: int | None = None,
) -> PortfolioSnapshot:
    position = calculate_position(db, portfolio.id, asset_id)
    liquidation_value = _money(position.quantity * mark_price)
    portfolio_value = _money(portfolio.cash_balance + liquidation_value)
    realized_pnl = _money(position.sell_net_amount - (position.average_buy_cost * position.sell_quantity))
    unrealized_pnl = _money(liquidation_value - (position.average_buy_cost * position.quantity))

    snapshot = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        price_snapshot_id=price_snapshot_id,
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


def _latest_price_snapshot_id(db: Session, asset_id: int) -> int | None:
    return db.execute(
        select(PriceSnapshot.id)
        .where(PriceSnapshot.asset_id == asset_id)
        .order_by(PriceSnapshot.observed_at.desc(), PriceSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _inject_provider_costs(
    db: Session,
    *,
    request: PaperTradeRequest,
    portfolio: Portfolio,
    asset: Asset,
) -> None:
    price = request.buy_price if request.action == "paper_buy" else request.sell_price
    is_buy = request.action == "paper_buy"
    provider = _resolve_portfolio_provider(db, portfolio)
    rule = _resolve_provider_cost_rule(db, provider=provider, asset=asset, action=request.action)

    if rule is not None:
        if request.quantity is not None:
            costs = _calculate_provider_rule_costs(rule, quantity=request.quantity, price=price)
        elif request.cash_amount is not None and is_buy:
            qty = _quantity_from_cash_amount(request.cash_amount, price=price, rule=rule)
            costs = _calculate_provider_rule_costs(rule, quantity=qty, price=price)
        else:
            return

        if request.fees == 0:
            request.fees = costs.fees
        if request.taxes == 0:
            request.taxes = costs.taxes
        return

    settings = get_settings()
    if asset.symbol != settings.auto_trading_asset_symbol:
        return

    cost_model_key = _resolve_legacy_cost_model_key(provider)
    cost_model = COST_MODEL_REGISTRY[cost_model_key]
    if request.quantity is not None:
        qty = request.quantity
        if request.fees == 0:
            request.fees = _money(cost_model.calculate_fees(qty, price, is_buy))
        if request.taxes == 0:
            request.taxes = _money(cost_model.calculate_taxes(qty, price, is_buy))
    elif request.cash_amount is not None and is_buy and request.fees == 0 and request.taxes == 0:
        cost_ratio = cost_model.calculate_cost(Decimal("1.0"), Decimal("1.0"))
        factor = Decimal("1.0") + cost_ratio
        gross = request.cash_amount / factor
        qty = gross / price
        request.fees = _money(cost_model.calculate_fees(qty, price, is_buy))
        request.taxes = _money(cost_model.calculate_taxes(qty, price, is_buy))


def _resolve_portfolio_provider(db: Session, portfolio: Portfolio) -> Provider | None:
    provider = db.execute(
        select(Provider)
        .join(TenantPortfolio, TenantPortfolio.provider_id == Provider.id)
        .where(TenantPortfolio.portfolio_id == portfolio.id, TenantPortfolio.is_active.is_(True))
        .order_by(TenantPortfolio.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if provider is not None:
        return provider

    settings = get_settings()
    return db.execute(select(Provider).where(Provider.name == settings.default_provider_name)).scalar_one_or_none()


def _resolve_legacy_cost_model_key(provider: Provider | None) -> str:
    settings = get_settings()
    if provider is not None and provider.name in COST_MODEL_REGISTRY:
        return provider.name
    if settings.default_provider_name in COST_MODEL_REGISTRY:
        return settings.default_provider_name
    return "kuveyt_turk"


def _resolve_provider_cost_rule(
    db: Session,
    *,
    provider: Provider | None,
    asset: Asset,
    action: str,
) -> ProviderCostRule | None:
    if provider is None:
        return None

    now = datetime.now(UTC)
    rules = (
        db.execute(
            select(ProviderCostRule)
            .where(
                ProviderCostRule.provider_id == provider.id,
                ProviderCostRule.is_active.is_(True),
                ProviderCostRule.action.in_([action, "*"]),
                or_(ProviderCostRule.asset_id == asset.id, ProviderCostRule.asset_id.is_(None)),
                or_(ProviderCostRule.asset_type == asset.asset_type, ProviderCostRule.asset_type.is_(None)),
            )
            .order_by(ProviderCostRule.asset_id.desc(), ProviderCostRule.asset_type.desc(), ProviderCostRule.id.desc())
        )
        .scalars()
        .all()
    )

    for rule in rules:
        if rule.effective_from is not None and _as_aware(rule.effective_from) > now:
            continue
        if rule.effective_to is not None and _as_aware(rule.effective_to) <= now:
            continue
        return rule
    return None


def _calculate_provider_rule_costs(
    rule: ProviderCostRule,
    *,
    quantity: Decimal,
    price: Decimal,
) -> ProviderCostRuleCosts:
    gross = _money(quantity * price)
    fees = _money(gross * Decimal(rule.fee_rate) + Decimal(rule.fixed_fee))
    taxes = _money(gross * Decimal(rule.tax_rate))
    return ProviderCostRuleCosts(fees=fees, taxes=taxes)


def _quantity_from_cash_amount(cash_amount: Decimal, *, price: Decimal, rule: ProviderCostRule) -> Decimal:
    fixed_fee = Decimal(rule.fixed_fee)
    spendable = cash_amount - fixed_fee
    if spendable <= 0:
        raise PaperTradingError("cash_amount must exceed fixed provider fees")
    variable_factor = Decimal("1.0") + Decimal(rule.fee_rate) + Decimal(rule.tax_rate)
    return (spendable / (price * variable_factor)).quantize(MONEY_QUANT, rounding=ROUND_DOWN)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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


def _calculate_cost_breakdown(
    request: PaperTradeRequest,
    *,
    quantity: Decimal,
    gross_amount: Decimal,
    net_amount: Decimal,
) -> TradeCostBreakdown:
    buy_price = _money(request.buy_price)
    sell_price = _money(request.sell_price)
    mid_price = _money((buy_price + sell_price) / Decimal("2")) if buy_price and sell_price else Decimal("0")
    midpoint_amount = _money(quantity * mid_price) if mid_price > 0 else gross_amount
    sign = 1 if request.action == "paper_buy" else (-1 if request.action == "paper_sell" else 0)
    spread_impact = _money(sign * (gross_amount - midpoint_amount))
    return TradeCostBreakdown(
        gross_amount=gross_amount,
        fees=_money(request.fees),
        taxes=_money(request.taxes),
        spread_impact=spread_impact,
        net_amount=net_amount,
        mid_price=mid_price,
    )


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
