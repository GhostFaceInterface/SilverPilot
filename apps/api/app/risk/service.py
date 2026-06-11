import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.service import collector_health
from app.core.config import get_settings
from app.models import Asset, MLInferenceAudit, PaperTrade, Portfolio, RawGlobalPrice, RiskDecision
from app.schemas.paper_trading import PaperTradeRequest
from app.services.base import BaseRiskGuard

CONFIDENCE = Decimal("1.0000")
PERCENT_QUANT = Decimal("0.000001")
NEAR_LIMIT_USED_PERCENT = Decimal("80.000000")


def is_comex_weekend(dt: datetime) -> bool:
    """Returns True only during actual COMEX weekend closure: Friday 17:00 ET to Sunday 18:00 ET."""
    settings = get_settings()
    if settings.app_env == "test":
        return False

    from zoneinfo import ZoneInfo

    et_tz = ZoneInfo("America/New_York")
    et_dt = dt.astimezone(et_tz)
    weekday = et_dt.weekday()  # 0 = Monday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday
    hour = et_dt.hour

    return (weekday == 4 and hour >= 17) or (weekday == 5) or (weekday == 6 and hour < 18)


def is_comex_maintenance(dt: datetime) -> bool:
    """Returns True during weekday daily maintenance window: Mon-Thu 17:00-18:00 ET."""
    settings = get_settings()
    if settings.app_env == "test":
        return False

    from zoneinfo import ZoneInfo

    et_tz = ZoneInfo("America/New_York")
    et_dt = dt.astimezone(et_tz)
    weekday = et_dt.weekday()
    hour = et_dt.hour

    return weekday in {0, 1, 2, 3} and hour == 17


def is_comex_market_closed(dt: datetime) -> bool:
    """
    Checks if the COMEX precious metals market is closed.
    COMEX trading hours: Sun 18:00 ET to Fri 17:00 ET.
    Daily maintenance window: 17:00 to 18:00 ET.
    """
    return is_comex_weekend(dt) or is_comex_maintenance(dt)


@dataclass(frozen=True)
class TradeAmounts:
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    net_amount: Decimal


@dataclass(frozen=True)
class GlobalPriceRangeMetric:
    percent: Decimal
    source: str
    sample_count: int
    min_price: Decimal
    max_price: Decimal


@dataclass(frozen=True)
class GlobalPriceRiseMetric:
    percent: Decimal
    source: str
    sample_count: int
    first_price: Decimal
    latest_price: Decimal


class PositionLike(Protocol):
    quantity: Decimal


class RiskStatusError(Exception):
    pass


class SpreadRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        request = context["request"]
        settings = get_settings()
        return _spread_block(db, request=request, max_spread_percent=settings.risk_max_spread_percent)


class StalenessRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        now = context.get("now")
        settings = get_settings()
        return _execution_data_block(db, stale_after_minutes=settings.risk_data_stale_after_minutes, now=now)


class LossLimitRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        portfolio = context["portfolio"]
        asset = context["asset"]
        settings = get_settings()
        return _loss_limit_block(
            db,
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            max_daily_loss_usd=settings.risk_max_daily_loss_usd,
            max_weekly_loss_usd=settings.risk_max_weekly_loss_usd,
        )


class VolatilityRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        asset = context["asset"]
        settings = get_settings()
        return _volatility_block(
            db,
            asset_id=asset.id,
            max_24h_percent=settings.risk_max_24h_volatility_percent,
            max_7d_percent=settings.risk_max_7d_volatility_percent,
        )


class FomoRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        request = context["request"]
        asset = context["asset"]
        settings = get_settings()
        return _fomo_block(
            db,
            request=request,
            asset_id=asset.id,
            lookback_minutes=settings.risk_fomo_lookback_minutes,
            max_rise_percent=settings.risk_fomo_rise_percent,
        )


class ExpectedGainRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        request = context["request"]
        amounts = context["amounts"]
        settings = get_settings()
        return _expected_gain_block(
            db,
            request=request,
            amounts=amounts,
            min_expected_net_gain_percent=settings.risk_min_expected_net_gain_percent,
        )


class MlModelRiskGuard(BaseRiskGuard):
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision | None:
        request = context["request"]
        asset = context["asset"]
        ml_decision, ml_advisory_details = _ml_model_review(db, request=request, asset_id=asset.id)
        context["ml_advisory"] = ml_advisory_details
        return ml_decision


RISK_GUARDS = [
    SpreadRiskGuard(),
    StalenessRiskGuard(),
    LossLimitRiskGuard(),
    VolatilityRiskGuard(),
    FomoRiskGuard(),
    ExpectedGainRiskGuard(),
    MlModelRiskGuard(),
]


def evaluate_paper_trade_risk(
    db: Session,
    *,
    request: PaperTradeRequest,
    portfolio: Portfolio,
    asset: Asset,
    position: PositionLike,
    amounts: TradeAmounts,
    now: datetime | None = None,
) -> RiskDecision:
    if now is None:
        now = datetime.now(UTC)
    settings = get_settings()

    if request.action == "hold":
        return _decision(
            db,
            decision="hold",
            reason_code="HOLD_REQUESTED",
            risk_level="low",
            details={"requested_action": request.action},
        )
    if request.action == "blocked":
        return _decision(
            db,
            decision="blocked",
            reason_code="BLOCKED_REQUESTED",
            risk_level="low",
            details={"requested_action": request.action},
        )

    context = {
        "request": request,
        "portfolio": portfolio,
        "asset": asset,
        "position": position,
        "amounts": amounts,
        "now": now,
        "ml_advisory": None,
    }

    # Run each guard in turn
    for guard in RISK_GUARDS:
        decision = guard.evaluate_risk(db, context)
        if decision is not None:
            return decision

    if request.action == "paper_buy" and portfolio.cash_balance < amounts.net_amount:
        return _decision(
            db,
            decision="blocked",
            reason_code="INSUFFICIENT_CASH",
            risk_level="high",
            details={
                "cash_balance": str(portfolio.cash_balance),
                "required_cash": str(amounts.net_amount),
                "asset_symbol": asset.symbol,
            },
        )

    if request.action == "paper_sell" and position.quantity < amounts.quantity:
        return _decision(
            db,
            decision="blocked",
            reason_code="POSITION_LIMIT_REACHED",
            risk_level="high",
            details={
                "available_quantity": str(position.quantity),
                "requested_quantity": str(amounts.quantity),
                "asset_symbol": asset.symbol,
            },
        )

    return _decision(
        db,
        decision="allow",
        reason_code="RISK_CHECK_PASSED",
        risk_level="low",
        details={
            "asset_symbol": asset.symbol,
            "requested_action": request.action,
            "max_spread_percent": str(settings.risk_max_spread_percent),
            "data_stale_after_minutes": settings.risk_data_stale_after_minutes,
            "max_24h_volatility_percent": str(settings.risk_max_24h_volatility_percent),
            "max_7d_volatility_percent": str(settings.risk_max_7d_volatility_percent),
            "fomo_lookback_minutes": settings.risk_fomo_lookback_minutes,
            "fomo_rise_percent": str(settings.risk_fomo_rise_percent),
            "max_daily_loss_usd": str(settings.risk_max_daily_loss_usd),
            "max_weekly_loss_usd": str(settings.risk_max_weekly_loss_usd),
            "ml_advisory": context.get("ml_advisory"),
        },
    )


def risk_policy_status(
    db: Session,
    *,
    portfolio_name: str = "gram-paper",
    asset_symbol: str = "XAG_GRAM",
) -> dict:
    settings = get_settings()
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == portfolio_name)).scalar_one_or_none()
    if portfolio is None:
        raise RiskStatusError("Portfolio not found")
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        raise RiskStatusError("Asset not found")

    now = datetime.now(UTC)
    daily_loss = _realized_loss_since(db, portfolio_id=portfolio.id, asset_id=asset.id, since=now - timedelta(days=1))
    weekly_loss = _realized_loss_since(db, portfolio_id=portfolio.id, asset_id=asset.id, since=now - timedelta(days=7))
    volatility_24h_metric = _global_price_range_metric(db, asset_id=asset.id, since=now - timedelta(hours=24))
    volatility_7d_metric = _global_price_range_metric(db, asset_id=asset.id, since=now - timedelta(days=7))
    fomo_rise_metric = _global_price_rise_metric(
        db,
        asset_id=asset.id,
        since=now - timedelta(minutes=settings.risk_fomo_lookback_minutes),
    )
    volatility_24h = volatility_24h_metric.percent if volatility_24h_metric is not None else None
    volatility_7d = volatility_7d_metric.percent if volatility_7d_metric is not None else None
    fomo_rise = fomo_rise_metric.percent if fomo_rise_metric is not None else None

    would_block_now = []
    if daily_loss >= settings.risk_max_daily_loss_usd:
        would_block_now.append(
            {
                "reason_code": "DAILY_LOSS_LIMIT_REACHED",
                "risk_level": "high",
                "metric": str(daily_loss),
                "threshold": str(settings.risk_max_daily_loss_usd),
            }
        )
    if weekly_loss >= settings.risk_max_weekly_loss_usd:
        would_block_now.append(
            {
                "reason_code": "WEEKLY_LOSS_LIMIT_REACHED",
                "risk_level": "high",
                "metric": str(weekly_loss),
                "threshold": str(settings.risk_max_weekly_loss_usd),
            }
        )
    if volatility_24h is not None and volatility_24h > settings.risk_max_24h_volatility_percent:
        would_block_now.append(
            {
                "reason_code": "VOLATILITY_TOO_HIGH",
                "risk_level": "high",
                "metric": str(volatility_24h),
                "threshold": str(settings.risk_max_24h_volatility_percent),
                "window_hours": 24,
                "source": volatility_24h_metric.source,
                "sample_count": volatility_24h_metric.sample_count,
            }
        )
    if volatility_7d is not None and volatility_7d > settings.risk_max_7d_volatility_percent:
        would_block_now.append(
            {
                "reason_code": "VOLATILITY_TOO_HIGH",
                "risk_level": "high",
                "metric": str(volatility_7d),
                "threshold": str(settings.risk_max_7d_volatility_percent),
                "window_hours": 168,
                "source": volatility_7d_metric.source,
                "sample_count": volatility_7d_metric.sample_count,
            }
        )
    if fomo_rise is not None and fomo_rise > settings.risk_fomo_rise_percent:
        would_block_now.append(
            {
                "reason_code": "FOMO_RISK",
                "risk_level": "medium",
                "metric": str(fomo_rise),
                "threshold": str(settings.risk_fomo_rise_percent),
                "lookback_minutes": settings.risk_fomo_lookback_minutes,
                "source": fomo_rise_metric.source,
                "sample_count": fomo_rise_metric.sample_count,
            }
        )

    threshold_headroom = [
        _threshold_headroom_item(
            metric_name="daily_realized_loss_usd",
            reason_code="DAILY_LOSS_LIMIT_REACHED",
            risk_level="high",
            metric=daily_loss,
            threshold=settings.risk_max_daily_loss_usd,
            blocks_at_or_above=True,
        ),
        _threshold_headroom_item(
            metric_name="weekly_realized_loss_usd",
            reason_code="WEEKLY_LOSS_LIMIT_REACHED",
            risk_level="high",
            metric=weekly_loss,
            threshold=settings.risk_max_weekly_loss_usd,
            blocks_at_or_above=True,
        ),
        _threshold_headroom_item(
            metric_name="global_xag_volatility_24h_percent",
            reason_code="VOLATILITY_TOO_HIGH",
            risk_level="high",
            metric=volatility_24h,
            threshold=settings.risk_max_24h_volatility_percent,
            blocks_at_or_above=False,
            window_hours=24,
            source=volatility_24h_metric.source if volatility_24h_metric else None,
            sample_count=volatility_24h_metric.sample_count if volatility_24h_metric else None,
        ),
        _threshold_headroom_item(
            metric_name="global_xag_volatility_7d_percent",
            reason_code="VOLATILITY_TOO_HIGH",
            risk_level="high",
            metric=volatility_7d,
            threshold=settings.risk_max_7d_volatility_percent,
            blocks_at_or_above=False,
            window_hours=24 * 7,
            source=volatility_7d_metric.source if volatility_7d_metric else None,
            sample_count=volatility_7d_metric.sample_count if volatility_7d_metric else None,
        ),
        _threshold_headroom_item(
            metric_name="fomo_rise_percent",
            reason_code="FOMO_RISK",
            risk_level="medium",
            metric=fomo_rise,
            threshold=settings.risk_fomo_rise_percent,
            blocks_at_or_above=False,
            lookback_minutes=settings.risk_fomo_lookback_minutes,
            source=fomo_rise_metric.source if fomo_rise_metric else None,
            sample_count=fomo_rise_metric.sample_count if fomo_rise_metric else None,
        ),
    ]

    return {
        "portfolio_name": portfolio.name,
        "asset_symbol": asset.symbol,
        "thresholds": {
            "data_stale_after_minutes": settings.risk_data_stale_after_minutes,
            "max_spread_percent": settings.risk_max_spread_percent,
            "max_24h_volatility_percent": settings.risk_max_24h_volatility_percent,
            "max_7d_volatility_percent": settings.risk_max_7d_volatility_percent,
            "fomo_lookback_minutes": settings.risk_fomo_lookback_minutes,
            "fomo_rise_percent": settings.risk_fomo_rise_percent,
            "max_daily_loss_usd": settings.risk_max_daily_loss_usd,
            "max_weekly_loss_usd": settings.risk_max_weekly_loss_usd,
            "min_expected_net_gain_percent": settings.risk_min_expected_net_gain_percent,
        },
        "current_metrics": {
            "global_xag_volatility_24h_percent": volatility_24h,
            "global_xag_volatility_24h_source": volatility_24h_metric.source if volatility_24h_metric else None,
            "global_xag_volatility_24h_sample_count": (
                volatility_24h_metric.sample_count if volatility_24h_metric else None
            ),
            "global_xag_volatility_7d_percent": volatility_7d,
            "global_xag_volatility_7d_source": volatility_7d_metric.source if volatility_7d_metric else None,
            "global_xag_volatility_7d_sample_count": volatility_7d_metric.sample_count
            if volatility_7d_metric
            else None,
            "fomo_rise_percent": fomo_rise,
            "fomo_rise_source": fomo_rise_metric.source if fomo_rise_metric else None,
            "fomo_rise_sample_count": fomo_rise_metric.sample_count if fomo_rise_metric else None,
            "daily_realized_loss_usd": daily_loss,
            "weekly_realized_loss_usd": weekly_loss,
        },
        "would_block_now": would_block_now,
        "threshold_headroom": threshold_headroom,
        "recent_decisions": _recent_risk_decision_counts(db, since=now - timedelta(hours=24)),
        "global_xag_diagnostics": [
            _global_price_window_summary(db, asset_id=asset.id, since=now - timedelta(hours=24), window_hours=24),
            _global_price_window_summary(db, asset_id=asset.id, since=now - timedelta(days=7), window_hours=24 * 7),
        ],
    }


def _spread_block(db: Session, *, request: PaperTradeRequest, max_spread_percent: Decimal) -> RiskDecision | None:
    if request.buy_price <= 0 or request.sell_price <= 0:
        return None
    mid_price = (request.buy_price + request.sell_price) / Decimal("2")
    if mid_price <= 0:
        return None
    spread_percent = ((request.buy_price - request.sell_price) / mid_price) * Decimal("100")
    if spread_percent <= max_spread_percent:
        return None
    return _decision(
        db,
        decision="blocked",
        reason_code="SPREAD_TOO_HIGH",
        risk_level="high",
        details={
            "spread_percent": str(spread_percent.quantize(Decimal("0.000001"))),
            "max_spread_percent": str(max_spread_percent),
        },
    )


def _execution_data_block(db: Session, *, stale_after_minutes: int, now: datetime | None = None) -> RiskDecision | None:
    if now is None:
        now = datetime.now(UTC)
    health = collector_health(db, stale_after_minutes=stale_after_minutes, now=now)
    execution_status = health["execution_critical_status"]
    if execution_status not in {"blocked", "stale"}:
        return None

    execution_critical = health["execution_critical"]
    reason_code = "MISSING_DATA" if execution_status == "blocked" else "STALE_DATA"
    return _decision(
        db,
        decision="blocked",
        reason_code=reason_code,
        risk_level="high",
        details={
            "execution_critical_status": execution_status,
            "bank_price": execution_critical["bank_price"],
            "bank_price_source": execution_critical["source"],
            "bank_price_age_seconds": execution_critical["age_seconds"],
            "global_xag_usd": execution_critical["global_xag_usd"],
            "global_xag_source": execution_critical["global_xag_source"],
            "global_xag_age_seconds": execution_critical["global_xag_age_seconds"],
            "global_xag_observed_age_seconds": execution_critical.get("observed_age_seconds"),
            "usd_try": execution_critical["usd_try"],
            "usd_try_source": execution_critical["usd_try_source"],
            "usd_try_age_seconds": execution_critical["usd_try_age_seconds"],
            "stale_after_minutes": stale_after_minutes,
        },
    )


def _loss_limit_block(
    db: Session,
    *,
    portfolio_id: int,
    asset_id: int,
    max_daily_loss_usd: Decimal,
    max_weekly_loss_usd: Decimal,
) -> RiskDecision | None:
    now = datetime.now(UTC)
    daily_loss = _realized_loss_since(db, portfolio_id=portfolio_id, asset_id=asset_id, since=now - timedelta(days=1))
    if daily_loss >= max_daily_loss_usd:
        return _decision(
            db,
            decision="blocked",
            reason_code="DAILY_LOSS_LIMIT_REACHED",
            risk_level="high",
            details={
                "realized_loss_usd": str(daily_loss),
                "max_daily_loss_usd": str(max_daily_loss_usd),
                "window_hours": 24,
            },
        )

    weekly_loss = _realized_loss_since(db, portfolio_id=portfolio_id, asset_id=asset_id, since=now - timedelta(days=7))
    if weekly_loss >= max_weekly_loss_usd:
        return _decision(
            db,
            decision="blocked",
            reason_code="WEEKLY_LOSS_LIMIT_REACHED",
            risk_level="high",
            details={
                "realized_loss_usd": str(weekly_loss),
                "max_weekly_loss_usd": str(max_weekly_loss_usd),
                "window_days": 7,
            },
        )
    return None


def _volatility_block(
    db: Session,
    *,
    asset_id: int,
    max_24h_percent: Decimal,
    max_7d_percent: Decimal,
) -> RiskDecision | None:
    for hours, max_percent in ((24, max_24h_percent), (24 * 7, max_7d_percent)):
        metric = _global_price_range_metric(db, asset_id=asset_id, since=datetime.now(UTC) - timedelta(hours=hours))
        if metric is None or metric.percent <= max_percent:
            continue
        return _decision(
            db,
            decision="blocked",
            reason_code="VOLATILITY_TOO_HIGH",
            risk_level="high",
            details={
                "window_hours": hours,
                "volatility_percent": str(metric.percent),
                "max_volatility_percent": str(max_percent),
                "source": metric.source,
                "sample_count": metric.sample_count,
                "min_price": str(metric.min_price),
                "max_price": str(metric.max_price),
            },
        )
    return None


def _fomo_block(
    db: Session,
    *,
    request: PaperTradeRequest,
    asset_id: int,
    lookback_minutes: int,
    max_rise_percent: Decimal,
) -> RiskDecision | None:
    if request.action != "paper_buy":
        return None

    since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    metric = _global_price_rise_metric(db, asset_id=asset_id, since=since)
    if metric is None or metric.percent <= max_rise_percent:
        return None
    return _decision(
        db,
        decision="blocked",
        reason_code="FOMO_RISK",
        risk_level="medium",
        details={
            "lookback_minutes": lookback_minutes,
            "rise_percent": str(metric.percent.quantize(PERCENT_QUANT)),
            "max_rise_percent": str(max_rise_percent),
            "source": metric.source,
            "sample_count": metric.sample_count,
            "first_price": str(metric.first_price),
            "latest_price": str(metric.latest_price),
        },
    )


def _expected_gain_block(
    db: Session,
    *,
    request: PaperTradeRequest,
    amounts: TradeAmounts,
    min_expected_net_gain_percent: Decimal,
) -> RiskDecision | None:
    if request.action != "paper_buy" or request.expected_exit_price is None:
        return None
    expected_exit_amount = amounts.quantity * request.expected_exit_price
    expected_net_gain = expected_exit_amount - amounts.net_amount
    if amounts.net_amount <= 0:
        return None
    expected_net_gain_percent = (expected_net_gain / amounts.net_amount) * Decimal("100")
    if expected_net_gain_percent > min_expected_net_gain_percent:
        return None
    return _decision(
        db,
        decision="blocked",
        reason_code="EXPECTED_GAIN_BELOW_COST",
        risk_level="medium",
        details={
            "expected_exit_price": str(request.expected_exit_price),
            "expected_net_gain": str(expected_net_gain.quantize(Decimal("0.000001"))),
            "expected_net_gain_percent": str(expected_net_gain_percent.quantize(PERCENT_QUANT)),
            "min_expected_net_gain_percent": str(min_expected_net_gain_percent),
        },
    )


def _ml_model_review(
    db: Session, *, request: PaperTradeRequest, asset_id: int
) -> tuple[RiskDecision | None, dict | None]:
    settings = get_settings()
    if not settings.risk_ml_model_enabled:
        return None, None
    if request.action != "paper_buy":
        return None, None

    try:
        from app.ml.inference import predict_profitability_details

        result = predict_profitability_details(db, asset_id=asset_id)
        audit = _record_ml_inference_audit(db, asset_id=asset_id, result=result)
        advisory_details = _ml_advisory_details(result=result, audit_id=audit.id)
        if result.probability is None:
            return None, advisory_details  # Graceful fallback: allow trade if inference fails / model missing

        if result.probability < result.threshold and result.decision_mode == "hard_veto":
            decision = _decision(
                db,
                decision="blocked",
                reason_code="ML_UNPROFITABLE_PREDICTION",
                risk_level="medium",
                details={
                    "predicted_probability": f"{result.probability:.4f}",
                    "min_probability_threshold": f"{result.threshold:.4f}",
                    "decision_mode": result.decision_mode,
                    "ml_inference_audit_id": audit.id,
                    "asset_id": asset_id,
                },
            )
            audit.risk_decision_id = decision.id
            db.flush()
            return decision, advisory_details
        return None, advisory_details
    except Exception as e:
        logger = logging.getLogger("silverpilot.ml.veto")
        logger.error(f"Graceful bypass triggered in ML veto block due to exception: {e}")

    return None, None


def _record_ml_inference_audit(db: Session, *, asset_id: int, result: Any) -> MLInferenceAudit:
    metadata = result.model_metadata or {}
    audit = MLInferenceAudit(
        asset_id=asset_id,
        model_run_id=metadata.get("run_id"),
        model_status=metadata.get("model_status", "unknown"),
        model_target=metadata.get("target"),
        decision_mode=result.decision_mode,
        recommendation=result.recommendation,
        predicted_probability=Decimal(str(result.probability)) if result.probability is not None else None,
        threshold=Decimal(str(result.threshold)) if result.threshold is not None else None,
        feature_snapshot=result.feature_snapshot,
        details_json=result.details,
    )
    db.add(audit)
    db.flush()
    return audit


def _ml_advisory_details(*, result: Any, audit_id: int) -> dict:
    details = {
        "decision_mode": result.decision_mode,
        "recommendation": result.recommendation,
        "ml_inference_audit_id": audit_id,
        "model_run_id": result.model_metadata.get("run_id") if result.model_metadata else None,
    }
    if result.probability is not None:
        details["predicted_probability"] = f"{result.probability:.4f}"
    if result.threshold is not None:
        details["min_probability_threshold"] = f"{result.threshold:.4f}"
    return details


def _threshold_headroom_item(
    *,
    metric_name: str,
    reason_code: str,
    risk_level: str,
    metric: Decimal | None,
    threshold: Decimal,
    blocks_at_or_above: bool,
    window_hours: int | None = None,
    lookback_minutes: int | None = None,
    source: str | None = None,
    sample_count: int | None = None,
) -> dict:
    if metric is None:
        return {
            "metric_name": metric_name,
            "reason_code": reason_code,
            "risk_level": risk_level,
            "metric": None,
            "threshold": str(threshold),
            "remaining_to_block": None,
            "used_percent": None,
            "status": "insufficient_data",
            "window_hours": window_hours,
            "lookback_minutes": lookback_minutes,
            "source": source,
            "sample_count": sample_count,
        }

    used_percent = ((metric / threshold) * Decimal("100")).quantize(PERCENT_QUANT)
    remaining = max(threshold - metric, Decimal("0")).quantize(PERCENT_QUANT)
    blocked = metric >= threshold if blocks_at_or_above else metric > threshold
    status = "blocked" if blocked else "near_limit" if used_percent >= NEAR_LIMIT_USED_PERCENT else "ok"
    return {
        "metric_name": metric_name,
        "reason_code": reason_code,
        "risk_level": risk_level,
        "metric": str(metric),
        "threshold": str(threshold),
        "remaining_to_block": str(remaining),
        "used_percent": str(used_percent),
        "status": status,
        "window_hours": window_hours,
        "lookback_minutes": lookback_minutes,
        "source": source,
        "sample_count": sample_count,
    }


def _global_price_range_metric(db: Session, *, asset_id: int, since: datetime) -> GlobalPriceRangeMetric | None:
    rows = _global_price_rows_since(db, asset_id=asset_id, since=since)
    prices_by_source: dict[str, list[Decimal]] = {}
    for row in rows:
        prices_by_source.setdefault(row.source, []).append(_global_mid_price(row))

    candidates: list[GlobalPriceRangeMetric] = []
    for source, prices in prices_by_source.items():
        range_percent = _price_range_percent(prices)
        if range_percent is None:
            continue
        candidates.append(
            GlobalPriceRangeMetric(
                percent=range_percent,
                source=source,
                sample_count=len(prices),
                min_price=min(prices),
                max_price=max(prices),
            )
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.percent, item.sample_count, item.source))


def _price_range_percent(prices: list[Decimal]) -> Decimal | None:
    if len(prices) < 2:
        return None
    high_price = max(prices)
    low_price = min(prices)
    return _price_range_percent_from_bounds(low_price=low_price, high_price=high_price)


def _price_range_percent_from_bounds(*, low_price: Decimal, high_price: Decimal) -> Decimal | None:
    mid_price = (high_price + low_price) / Decimal("2")
    if mid_price <= 0:
        return None
    return (((high_price - low_price) / mid_price) * Decimal("100")).quantize(PERCENT_QUANT)


def _global_price_rise_metric(db: Session, *, asset_id: int, since: datetime) -> GlobalPriceRiseMetric | None:
    rows = _global_price_rows_since(db, asset_id=asset_id, since=since)
    prices_by_source: dict[str, list[Decimal]] = {}
    for row in rows:
        prices_by_source.setdefault(row.source, []).append(_global_mid_price(row))

    candidates: list[GlobalPriceRiseMetric] = []
    for source, prices in prices_by_source.items():
        rise_percent = _price_rise_percent(prices)
        if rise_percent is None:
            continue
        candidates.append(
            GlobalPriceRiseMetric(
                percent=rise_percent,
                source=source,
                sample_count=len(prices),
                first_price=prices[0],
                latest_price=prices[-1],
            )
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.percent, item.sample_count, item.source))


def _price_rise_percent(prices: list[Decimal]) -> Decimal | None:
    if len(prices) < 2:
        return None
    first_price = prices[0]
    latest_price = prices[-1]
    if first_price <= 0:
        return None
    return (((latest_price - first_price) / first_price) * Decimal("100")).quantize(PERCENT_QUANT)


def _global_price_rows_since(db: Session, *, asset_id: int, since: datetime) -> list[RawGlobalPrice]:
    return list(
        db.execute(
            select(RawGlobalPrice)
            .where(RawGlobalPrice.asset_id == asset_id, RawGlobalPrice.observed_at >= since)
            .order_by(RawGlobalPrice.observed_at.asc(), RawGlobalPrice.id.asc())
        ).scalars()
    )


def _global_mid_prices_since(db: Session, *, asset_id: int, since: datetime) -> list[Decimal]:
    return [_global_mid_price(row) for row in _global_price_rows_since(db, asset_id=asset_id, since=since)]


def _global_mid_price(row: RawGlobalPrice) -> Decimal:
    return ((row.buy_price + row.sell_price) / Decimal("2")).quantize(Decimal("0.000001"))


def _global_price_window_summary(db: Session, *, asset_id: int, since: datetime, window_hours: int) -> dict:
    rows = _global_price_rows_since(db, asset_id=asset_id, since=since)
    if not rows:
        return {
            "window_hours": window_hours,
            "sample_count": 0,
            "first_observed_at": None,
            "last_observed_at": None,
            "latest_source": None,
            "latest_price": None,
            "min_price": None,
            "max_price": None,
            "range_percent": None,
            "sources": [],
        }

    source_summaries: dict[str, dict] = {}
    prices: list[Decimal] = []
    for row in rows:
        price = _global_mid_price(row)
        prices.append(price)
        summary = source_summaries.setdefault(
            row.source,
            {
                "source": row.source,
                "sample_count": 0,
                "first_observed_at": row.observed_at,
                "last_observed_at": row.observed_at,
                "min_price": price,
                "max_price": price,
            },
        )
        summary["sample_count"] += 1
        summary["last_observed_at"] = row.observed_at
        summary["min_price"] = min(summary["min_price"], price)
        summary["max_price"] = max(summary["max_price"], price)

    latest_row = rows[-1]
    window_range = _price_range_percent(prices)
    return {
        "window_hours": window_hours,
        "sample_count": len(rows),
        "first_observed_at": rows[0].observed_at,
        "last_observed_at": latest_row.observed_at,
        "latest_source": latest_row.source,
        "latest_price": _global_mid_price(latest_row),
        "min_price": min(prices),
        "max_price": max(prices),
        "range_percent": window_range,
        "sources": [
            {
                **summary,
                "range_percent": _price_range_percent_from_bounds(
                    low_price=summary["min_price"],
                    high_price=summary["max_price"],
                ),
            }
            for summary in sorted(source_summaries.values(), key=lambda item: item["source"])
        ],
    }


def _realized_loss_since(db: Session, *, portfolio_id: int, asset_id: int, since: datetime) -> Decimal:
    trades = db.execute(
        select(
            PaperTrade.quantity,
            PaperTrade.net_amount,
            PaperTrade.action,
            PaperTrade.created_at,
        )
        .where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.asset_id == asset_id,
            PaperTrade.action.in_(("paper_buy", "paper_sell")),
        )
        .order_by(PaperTrade.created_at.asc(), PaperTrade.id.asc())
    ).all()

    buy_quantity = Decimal("0")
    buy_net_amount = Decimal("0")
    realized_loss = Decimal("0")
    for trade in trades:
        if trade.action == "paper_buy":
            buy_quantity += trade.quantity
            buy_net_amount += trade.net_amount
            continue
        if trade.action != "paper_sell" or buy_quantity <= 0:
            continue

        sell_quantity = min(trade.quantity, buy_quantity)
        average_buy_cost = buy_net_amount / buy_quantity
        sell_net_amount = trade.net_amount * (sell_quantity / trade.quantity)
        pnl = sell_net_amount - (average_buy_cost * sell_quantity)
        if _as_utc(trade.created_at) >= since and pnl < 0:
            realized_loss += abs(pnl)
        buy_quantity -= sell_quantity
        buy_net_amount -= average_buy_cost * sell_quantity

    return realized_loss.quantize(Decimal("0.000001"))


def _recent_risk_decision_counts(db: Session, *, since: datetime) -> list[dict]:
    rows = db.execute(
        select(RiskDecision.decision, RiskDecision.reason_code, func.count(RiskDecision.id))
        .where(RiskDecision.created_at >= since)
        .group_by(RiskDecision.decision, RiskDecision.reason_code)
        .order_by(func.count(RiskDecision.id).desc(), RiskDecision.reason_code.asc())
    ).all()
    return [
        {
            "decision": decision,
            "reason_code": reason_code,
            "count": count,
        }
        for decision, reason_code, count in rows
    ]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decision(
    db: Session,
    *,
    decision: str,
    reason_code: str,
    risk_level: str,
    details: dict,
) -> RiskDecision:
    risk_decision = RiskDecision(
        decision=decision,
        reason_code=reason_code,
        risk_level=risk_level,
        confidence=CONFIDENCE,
        details_json=details,
    )
    db.add(risk_decision)
    db.flush()
    return risk_decision
