from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from silverpilot.app.core.settings import Settings
from silverpilot.app.db.models import (
    BankInstrumentModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    PaperTradeModel,
    PriceQuoteModel,
    RiskDecisionModel,
    RuntimeTickModel,
    StrategyModel,
    StrategyRunModel,
    SystemHealthEventModel,
    TelegramBotStateModel,
    VirtualAccountModel,
)


@dataclass(frozen=True)
class SystemHealthSnapshot:
    status: str
    payload: dict[str, Any]


class SystemHealthService:
    def __init__(self, *, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def snapshot(self, *, now: datetime | None = None) -> SystemHealthSnapshot:
        captured_at = now or datetime.now(UTC)
        counts = {
            "accounts": self._count(VirtualAccountModel),
            "bank_instruments": self._count(BankInstrumentModel),
            "strategies": self._count(StrategyModel),
            "quotes": self._count(PriceQuoteModel),
            "bars": self._count(MarketBarModel),
            "indicators": self._count(IndicatorSnapshotModel),
            "regimes": self._count(MarketRegimeSnapshotModel),
            "strategy_runs": self._count(StrategyRunModel),
            "risk_decisions": self._count(RiskDecisionModel),
            "trades": self._count(PaperTradeModel),
        }
        latest = {
            "quote_at": _iso(self._latest(PriceQuoteModel.observed_at)),
            "bar_at": _iso(self._latest(MarketBarModel.bar_end_at)),
            "indicator_at": _iso(self._latest(IndicatorSnapshotModel.calculated_at)),
            "regime_at": _iso(self._latest(MarketRegimeSnapshotModel.confirmed_at)),
            "strategy_at": _iso(self._latest(StrategyRunModel.run_at)),
            "risk_at": _iso(self._latest(RiskDecisionModel.evaluated_at)),
            "trade_at": _iso(self._latest(PaperTradeModel.executed_at)),
        }
        latest_tick = self._session.scalar(
            select(RuntimeTickModel).order_by(RuntimeTickModel.finished_at.desc())
        )
        latest_event = self._session.scalar(
            select(SystemHealthEventModel).order_by(SystemHealthEventModel.occurred_at.desc())
        )
        telegram = self._session.scalar(
            select(TelegramBotStateModel).order_by(TelegramBotStateModel.created_at.desc())
        )
        seed_ready = (
            counts["accounts"] > 0 and counts["bank_instruments"] > 0 and counts["strategies"] > 0
        )
        runtime_status = latest_tick.status if latest_tick is not None else "not_started"
        warmup_progress = {
            "bars": counts["bars"],
            "required_bars": self._settings.runtime_warmup_bars,
            "complete": counts["bars"] >= self._settings.runtime_warmup_bars,
        }
        status = "ok"
        if not seed_ready:
            status = "degraded"
        elif self._settings.runtime_enabled and not warmup_progress["complete"]:
            status = "warming_up"
        if runtime_status == "failed":
            status = "failed"
        elif runtime_status == "warming_up":
            status = "warming_up"

        payload: dict[str, Any] = {
            "status": status,
            "app": self._settings.app_name,
            "captured_at": captured_at.isoformat(),
            "deployed_sha": self._settings.deployed_sha,
            "runtime_enabled": self._settings.runtime_enabled,
            "seed_ready": seed_ready,
            "counts": counts,
            "latest": latest,
            "warmup": warmup_progress,
            "runtime": {
                "status": runtime_status,
                "latest_tick_id": str(latest_tick.id) if latest_tick else None,
                "latest_tick_at": _iso(latest_tick.finished_at) if latest_tick else None,
                "summary": latest_tick.summary if latest_tick else None,
            },
            "last_event": {
                "component": latest_event.component if latest_event else None,
                "status": latest_event.status if latest_event else None,
                "message": latest_event.message if latest_event else None,
                "occurred_at": _iso(latest_event.occurred_at) if latest_event else None,
            },
            "telegram": {
                "enabled": self._settings.telegram_enabled,
                "status": telegram.status if telegram else "disabled",
                "last_update_id": telegram.last_update_id if telegram else None,
                "last_error": telegram.last_error if telegram else None,
            },
        }
        return SystemHealthSnapshot(status=status, payload=payload)

    def _count(self, model_type: type) -> int:
        return self._session.scalar(select(func.count()).select_from(model_type)) or 0

    def _latest(self, column: Any) -> datetime | None:
        return self._session.scalar(select(column).order_by(column.desc()).limit(1))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
