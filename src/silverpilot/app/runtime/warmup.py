from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import MarketBarModel
from silverpilot.app.domain.enums import IndicatorSourcePolicy, InstrumentType


@dataclass(frozen=True)
class WarmupProgress:
    bars: int
    eligible_bars: int
    total_bars: int
    required_bars: int
    complete: bool
    indicator_source_policy: str
    eligible_instrument_type: str | None
    eligible_instrument_id: UUID | None
    eligible_source: str | None
    eligible_timeframe: str | None
    reason: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "bars": self.bars,
            "eligible_bars": self.eligible_bars,
            "total_bars": self.total_bars,
            "required_bars": self.required_bars,
            "complete": self.complete,
            "indicator_source_policy": self.indicator_source_policy,
            "eligible_instrument_type": self.eligible_instrument_type,
            "eligible_instrument_id": str(self.eligible_instrument_id)
            if self.eligible_instrument_id
            else None,
            "eligible_source": self.eligible_source,
            "eligible_timeframe": self.eligible_timeframe,
            "reason": self.reason,
        }


def calculate_warmup_progress(
    session: Session,
    *,
    indicator_source_policy: IndicatorSourcePolicy,
    required_bars: int,
    execution_bar_instrument_id: UUID | None,
    execution_source: str | None,
    execution_timeframe: str | None,
    reference_instrument_id: UUID | None = None,
    reference_source: str | None = None,
    reference_timeframe: str | None = None,
) -> WarmupProgress:
    total_bars = _count_relevant_bars(
        session,
        execution_bar_instrument_id=execution_bar_instrument_id,
        execution_source=execution_source,
        execution_timeframe=execution_timeframe,
        reference_instrument_id=reference_instrument_id,
        reference_source=reference_source,
        reference_timeframe=reference_timeframe,
    )
    target = _eligible_target(
        indicator_source_policy=indicator_source_policy,
        execution_bar_instrument_id=execution_bar_instrument_id,
        execution_source=execution_source,
        execution_timeframe=execution_timeframe,
        reference_instrument_id=reference_instrument_id,
        reference_source=reference_source,
        reference_timeframe=reference_timeframe,
    )
    if target is None:
        return WarmupProgress(
            bars=0,
            eligible_bars=0,
            total_bars=total_bars,
            required_bars=required_bars,
            complete=False,
            indicator_source_policy=indicator_source_policy.value,
            eligible_instrument_type=None,
            eligible_instrument_id=None,
            eligible_source=None,
            eligible_timeframe=None,
            reason="reference_source_not_configured"
            if indicator_source_policy == IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
            else "execution_source_not_configured",
        )

    instrument_type, instrument_id, source, timeframe = target
    eligible_bars = _count_bars(
        session,
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        source=source,
        timeframe=timeframe,
    )
    return WarmupProgress(
        bars=eligible_bars,
        eligible_bars=eligible_bars,
        total_bars=total_bars,
        required_bars=required_bars,
        complete=eligible_bars >= required_bars,
        indicator_source_policy=indicator_source_policy.value,
        eligible_instrument_type=instrument_type.value,
        eligible_instrument_id=instrument_id,
        eligible_source=source,
        eligible_timeframe=timeframe,
        reason=None,
    )


def _eligible_target(
    *,
    indicator_source_policy: IndicatorSourcePolicy,
    execution_bar_instrument_id: UUID | None,
    execution_source: str | None,
    execution_timeframe: str | None,
    reference_instrument_id: UUID | None,
    reference_source: str | None,
    reference_timeframe: str | None,
) -> tuple[InstrumentType, UUID, str, str] | None:
    if indicator_source_policy == IndicatorSourcePolicy.REFERENCE_MARKET_FIRST:
        if reference_instrument_id is None or not reference_source or not reference_timeframe:
            return None
        return (
            InstrumentType.REFERENCE,
            reference_instrument_id,
            reference_source,
            reference_timeframe,
        )
    if execution_bar_instrument_id is None or not execution_source or not execution_timeframe:
        return None
    return (
        InstrumentType.EXECUTION,
        execution_bar_instrument_id,
        execution_source,
        execution_timeframe,
    )


def _count_relevant_bars(
    session: Session,
    *,
    execution_bar_instrument_id: UUID | None,
    execution_source: str | None,
    execution_timeframe: str | None,
    reference_instrument_id: UUID | None,
    reference_source: str | None,
    reference_timeframe: str | None,
) -> int:
    clauses = []
    if execution_bar_instrument_id is not None and execution_source and execution_timeframe:
        clauses.append(
            and_(
                MarketBarModel.instrument_type == InstrumentType.EXECUTION.value,
                MarketBarModel.instrument_id == execution_bar_instrument_id,
                MarketBarModel.source == execution_source,
                MarketBarModel.timeframe == execution_timeframe,
            )
        )
    if reference_instrument_id is not None and reference_source and reference_timeframe:
        clauses.append(
            and_(
                MarketBarModel.instrument_type == InstrumentType.REFERENCE.value,
                MarketBarModel.instrument_id == reference_instrument_id,
                MarketBarModel.source == reference_source,
                MarketBarModel.timeframe == reference_timeframe,
            )
        )
    if not clauses:
        return session.scalar(select(func.count(MarketBarModel.id))) or 0
    return session.scalar(select(func.count(MarketBarModel.id)).where(or_(*clauses))) or 0


def _count_bars(
    session: Session,
    *,
    instrument_type: InstrumentType,
    instrument_id: UUID,
    source: str,
    timeframe: str,
) -> int:
    return (
        session.scalar(
            select(func.count(MarketBarModel.id)).where(
                MarketBarModel.instrument_type == instrument_type.value,
                MarketBarModel.instrument_id == instrument_id,
                MarketBarModel.source == source,
                MarketBarModel.timeframe == timeframe,
            )
        )
        or 0
    )
