import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import IndicatorSnapshotModel, MarketBarModel
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.indicators.calculators import (
    BarLike,
    calculate_adx,
    calculate_atr,
    calculate_bollinger_band_width,
    calculate_ema,
    calculate_rsi,
)

IndicatorName = Literal["ema", "rsi", "atr", "adx", "bb_width"]


@dataclass(frozen=True)
class IndicatorSnapshotResult:
    snapshot: IndicatorSnapshotModel
    inserted: bool


class IndicatorService:
    """Calculates requested indicators from closed bars and caches snapshots."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def calculate_and_cache(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        indicator_name: IndicatorName,
        parameters: dict[str, object],
        source_bar_end_at: datetime,
        calculated_at: datetime,
    ) -> IndicatorSnapshotResult:
        if _aware_datetime(source_bar_end_at) > _aware_datetime(calculated_at):
            raise ValueError("source_bar_end_at cannot be after calculated_at")

        bars = list(
            self._session.scalars(
                select(MarketBarModel)
                .where(
                    MarketBarModel.instrument_type == instrument_type.value,
                    MarketBarModel.instrument_id == instrument_id,
                    MarketBarModel.source == source,
                    MarketBarModel.timeframe == timeframe,
                    MarketBarModel.bar_end_at <= source_bar_end_at,
                    or_(
                        MarketBarModel.signal_available_at.is_(None),
                        MarketBarModel.signal_available_at <= calculated_at,
                    ),
                )
                .order_by(MarketBarModel.bar_start_at.asc())
            )
        )
        if not bars:
            raise ValueError("cannot calculate indicator without bars")
        if not _timestamps_equal(bars[-1].bar_end_at, source_bar_end_at):
            gated_bar = self._session.scalar(
                select(MarketBarModel).where(
                    MarketBarModel.instrument_type == instrument_type.value,
                    MarketBarModel.instrument_id == instrument_id,
                    MarketBarModel.source == source,
                    MarketBarModel.timeframe == timeframe,
                    MarketBarModel.bar_end_at == source_bar_end_at,
                    MarketBarModel.signal_available_at.is_not(None),
                    MarketBarModel.signal_available_at > calculated_at,
                )
            )
            if gated_bar is not None:
                raise ValueError("source_bar_end_at is not yet signal-available")
            raise ValueError("source_bar_end_at must reference an available closed bar")

        normalized_parameters = _normalize_parameters(parameters)
        value = _calculate_indicator(indicator_name, bars, normalized_parameters)
        parameters_hash = hash_parameters(normalized_parameters)

        existing = self._session.scalar(
            select(IndicatorSnapshotModel).where(
                IndicatorSnapshotModel.instrument_type == instrument_type.value,
                IndicatorSnapshotModel.instrument_id == instrument_id,
                IndicatorSnapshotModel.source == source,
                IndicatorSnapshotModel.timeframe == timeframe,
                IndicatorSnapshotModel.indicator_name == indicator_name,
                IndicatorSnapshotModel.parameters_hash == parameters_hash,
                IndicatorSnapshotModel.source_bar_end_at == source_bar_end_at,
            )
        )
        values = {
            "parameters": normalized_parameters,
            "value": value,
            "calculated_at": calculated_at,
        }
        if existing is not None:
            for field_name, field_value in values.items():
                setattr(existing, field_name, field_value)
            existing.updated_at = calculated_at
            self._session.flush()
            return IndicatorSnapshotResult(snapshot=existing, inserted=False)

        snapshot = IndicatorSnapshotModel(
            instrument_type=instrument_type.value,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            indicator_name=indicator_name,
            parameters_hash=parameters_hash,
            source_bar_end_at=source_bar_end_at,
            created_at=calculated_at,
            **values,
        )
        self._session.add(snapshot)
        self._session.flush()
        return IndicatorSnapshotResult(snapshot=snapshot, inserted=True)


def hash_parameters(parameters: dict[str, object]) -> str:
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _calculate_indicator(
    indicator_name: IndicatorName,
    bars: list[MarketBarModel],
    parameters: dict[str, object],
) -> Decimal:
    bar_sequence = cast(Sequence[BarLike], bars)
    period = _required_int_parameter(parameters, "period")
    if indicator_name == "ema":
        return calculate_ema(bar_sequence, period=period)
    if indicator_name == "rsi":
        return calculate_rsi(bar_sequence, period=period)
    if indicator_name == "atr":
        return calculate_atr(bar_sequence, period=period)
    if indicator_name == "adx":
        return calculate_adx(bar_sequence, period=period)
    if indicator_name == "bb_width":
        standard_deviations = Decimal(str(parameters.get("standard_deviations", "2")))
        ddof = parameters.get("ddof", 1)
        if not isinstance(ddof, int):
            raise ValueError("ddof must be an integer")
        return calculate_bollinger_band_width(
            bar_sequence,
            period=period,
            standard_deviations=standard_deviations,
            ddof=ddof,
        )
    raise ValueError(f"unsupported indicator: {indicator_name}")


def _required_int_parameter(parameters: dict[str, object], name: str) -> int:
    value = parameters.get(name)
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _normalize_parameters(parameters: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(parameters, sort_keys=True, default=str))
    return cast(dict[str, object], normalized)


def _timestamps_equal(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None or right.tzinfo is None:
        return left.replace(tzinfo=None) == right.replace(tzinfo=None)
    return left == right


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
