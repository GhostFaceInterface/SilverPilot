from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime


@dataclass(frozen=True)
class RegimeDetectorConfig:
    config_version: str = "rule-v1"
    confirmation_bars: int = 2
    cooldown: timedelta = timedelta(hours=1)
    max_data_age: timedelta = timedelta(hours=2)
    trend_adx_threshold: Decimal = Decimal("25")
    range_adx_threshold: Decimal = Decimal("20")
    high_volatility_atr_threshold: Decimal = Decimal("2.5")
    low_volatility_atr_threshold: Decimal = Decimal("0.8")
    high_volatility_bb_width_threshold: Decimal = Decimal("10")
    low_volatility_bb_width_threshold: Decimal = Decimal("3")

    def __post_init__(self) -> None:
        if not self.config_version.strip():
            raise ValueError("config_version is required")
        if self.confirmation_bars < 1:
            raise ValueError("confirmation_bars must be at least 1")
        if self.cooldown < timedelta(0):
            raise ValueError("cooldown cannot be negative")
        if self.max_data_age <= timedelta(0):
            raise ValueError("max_data_age must be greater than zero")


@dataclass(frozen=True)
class RegimeDetectionResult:
    snapshot: MarketRegimeSnapshotModel
    inserted: bool


class RegimeDetector:
    """Classifies market regimes from closed bars and indicator snapshots."""

    def __init__(self, *, session: Session, config: RegimeDetectorConfig | None = None) -> None:
        self._session = session
        self._config = config or RegimeDetectorConfig()

    def detect_and_cache(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
        detected_at: datetime,
    ) -> RegimeDetectionResult:
        if source_bar_end_at > detected_at:
            raise ValueError("source_bar_end_at cannot be after detected_at")

        previous_snapshot = self._latest_previous_snapshot(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        candidate, confidence, evidence = self._classify_candidate(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
            detected_at=detected_at,
        )
        final_regime, starts_at, final_confidence = self._apply_transition_rules(
            candidate=candidate,
            confidence=confidence,
            evidence=evidence,
            previous_snapshot=previous_snapshot,
            source_bar_end_at=source_bar_end_at,
            detected_at=detected_at,
        )
        evidence["final_regime"] = final_regime.value
        evidence["config_version"] = self._config.config_version

        existing = self._session.scalar(
            select(MarketRegimeSnapshotModel).where(
                MarketRegimeSnapshotModel.instrument_type == instrument_type.value,
                MarketRegimeSnapshotModel.instrument_id == instrument_id,
                MarketRegimeSnapshotModel.source == source,
                MarketRegimeSnapshotModel.timeframe == timeframe,
                MarketRegimeSnapshotModel.source_bar_end_at == source_bar_end_at,
                MarketRegimeSnapshotModel.config_version == self._config.config_version,
            )
        )
        values = {
            "regime": final_regime.value,
            "confidence": final_confidence,
            "evidence": evidence,
            "starts_at": starts_at,
            "confirmed_at": detected_at,
        }
        if existing is not None:
            for field_name, field_value in values.items():
                setattr(existing, field_name, field_value)
            existing.updated_at = detected_at
            self._session.flush()
            return RegimeDetectionResult(snapshot=existing, inserted=False)

        snapshot = MarketRegimeSnapshotModel(
            instrument_type=instrument_type.value,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            config_version=self._config.config_version,
            source_bar_end_at=source_bar_end_at,
            created_at=detected_at,
            **values,
        )
        self._session.add(snapshot)
        self._session.flush()
        return RegimeDetectionResult(snapshot=snapshot, inserted=True)

    def _classify_candidate(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
        detected_at: datetime,
    ) -> tuple[MarketRegime, Decimal, dict[str, Any]]:
        bar = self._closed_bar(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        if bar is None:
            return self._no_trade("missing_closed_bar")
        if detected_at - source_bar_end_at > self._config.max_data_age:
            return self._no_trade("stale_bar")

        current = self._indicator_values(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            source_bar_end_at=source_bar_end_at,
        )
        if current.missing:
            return self._no_trade("missing_indicators", missing=current.missing)

        previous_ema_50 = self._previous_indicator_value(
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            source=source,
            timeframe=timeframe,
            indicator_name="ema",
            parameters_hash=current.parameters_hashes["ema_50"],
            source_bar_end_at=source_bar_end_at,
        )
        if previous_ema_50 is None:
            return self._no_trade("missing_ema_slope")

        ema_slope = current.values["ema_50"] - previous_ema_50
        evidence: dict[str, Any] = {
            "candidate_reasons": [],
            "indicator_values": {key: str(value) for key, value in current.values.items()},
            "ema_50_slope": str(ema_slope),
            "thresholds": self._threshold_evidence(),
        }

        if (
            current.values["atr_14"] >= self._config.high_volatility_atr_threshold
            or current.values["bb_width_20"] >= self._config.high_volatility_bb_width_threshold
        ):
            evidence["candidate_reasons"].append("volatility_above_threshold")
            return MarketRegime.HIGH_VOLATILITY, Decimal("0.80"), evidence

        if (
            current.values["atr_14"] <= self._config.low_volatility_atr_threshold
            and current.values["bb_width_20"] <= self._config.low_volatility_bb_width_threshold
        ):
            evidence["candidate_reasons"].append("volatility_compressed")
            return MarketRegime.LOW_VOLATILITY, Decimal("0.70"), evidence

        if (
            current.values["ema_50"] > current.values["ema_200"]
            and ema_slope > Decimal("0")
            and current.values["adx_14"] >= self._config.trend_adx_threshold
        ):
            evidence["candidate_reasons"].append("ema_uptrend_with_adx_confirmation")
            return MarketRegime.TREND_UP, Decimal("0.85"), evidence

        if (
            current.values["ema_50"] < current.values["ema_200"]
            and ema_slope < Decimal("0")
            and current.values["adx_14"] >= self._config.trend_adx_threshold
        ):
            evidence["candidate_reasons"].append("ema_downtrend_with_adx_confirmation")
            return MarketRegime.TREND_DOWN, Decimal("0.85"), evidence

        if current.values["adx_14"] <= self._config.range_adx_threshold:
            evidence["candidate_reasons"].append("adx_below_range_threshold")
            return MarketRegime.RANGE, Decimal("0.65"), evidence

        evidence["candidate_reasons"].append("rules_unconfirmed")
        return MarketRegime.NO_TRADE, Decimal("0"), evidence

    def _apply_transition_rules(
        self,
        *,
        candidate: MarketRegime,
        confidence: Decimal,
        evidence: dict[str, Any],
        previous_snapshot: MarketRegimeSnapshotModel | None,
        source_bar_end_at: datetime,
        detected_at: datetime,
    ) -> tuple[MarketRegime, datetime, Decimal]:
        evidence["candidate_regime"] = candidate.value
        if previous_snapshot is None or candidate == MarketRegime.NO_TRADE:
            return candidate, source_bar_end_at, confidence

        previous_regime = MarketRegime(previous_snapshot.regime)
        if candidate == previous_regime:
            return candidate, previous_snapshot.starts_at, confidence

        previous_confirmed_at = _aware_datetime(previous_snapshot.confirmed_at)
        previous_starts_at = _aware_datetime(previous_snapshot.starts_at)
        if detected_at - previous_confirmed_at < self._config.cooldown:
            evidence["transition_blocked"] = "cooldown"
            return previous_regime, previous_starts_at, Decimal(previous_snapshot.confidence)

        confirmations = 1 + self._prior_candidate_confirmation_count(
            candidate=candidate,
            previous_snapshot=previous_snapshot,
        )
        evidence["candidate_confirmations"] = confirmations
        if confirmations < self._config.confirmation_bars:
            evidence["transition_blocked"] = "hysteresis"
            return previous_regime, previous_starts_at, Decimal(previous_snapshot.confidence)

        evidence["transition_confirmed"] = True
        return candidate, source_bar_end_at, confidence

    def _closed_bar(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> MarketBarModel | None:
        return self._session.scalar(
            select(MarketBarModel).where(
                MarketBarModel.instrument_type == instrument_type.value,
                MarketBarModel.instrument_id == instrument_id,
                MarketBarModel.source == source,
                MarketBarModel.timeframe == timeframe,
                MarketBarModel.bar_end_at == source_bar_end_at,
            )
        )

    def _indicator_values(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> "_IndicatorLookup":
        snapshots = list(
            self._session.scalars(
                select(IndicatorSnapshotModel).where(
                    IndicatorSnapshotModel.instrument_type == instrument_type.value,
                    IndicatorSnapshotModel.instrument_id == instrument_id,
                    IndicatorSnapshotModel.source == source,
                    IndicatorSnapshotModel.timeframe == timeframe,
                    IndicatorSnapshotModel.source_bar_end_at == source_bar_end_at,
                )
            )
        )
        required: dict[str, tuple[str, dict[str, object]]] = {
            "ema_50": ("ema", {"period": 50}),
            "ema_200": ("ema", {"period": 200}),
            "adx_14": ("adx", {"period": 14}),
            "atr_14": ("atr", {"period": 14}),
            "bb_width_20": ("bb_width", {"period": 20}),
        }
        values: dict[str, Decimal] = {}
        parameters_hashes: dict[str, str] = {}
        missing: list[str] = []
        for key, (indicator_name, parameters) in required.items():
            snapshot = _find_indicator_snapshot(snapshots, indicator_name, parameters)
            if snapshot is None:
                missing.append(key)
                continue
            values[key] = Decimal(snapshot.value)
            parameters_hashes[key] = snapshot.parameters_hash
        return _IndicatorLookup(values=values, parameters_hashes=parameters_hashes, missing=missing)

    def _previous_indicator_value(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        indicator_name: str,
        parameters_hash: str,
        source_bar_end_at: datetime,
    ) -> Decimal | None:
        snapshot = self._session.scalar(
            select(IndicatorSnapshotModel)
            .where(
                IndicatorSnapshotModel.instrument_type == instrument_type.value,
                IndicatorSnapshotModel.instrument_id == instrument_id,
                IndicatorSnapshotModel.source == source,
                IndicatorSnapshotModel.timeframe == timeframe,
                IndicatorSnapshotModel.indicator_name == indicator_name,
                IndicatorSnapshotModel.parameters_hash == parameters_hash,
                IndicatorSnapshotModel.source_bar_end_at < source_bar_end_at,
            )
            .order_by(IndicatorSnapshotModel.source_bar_end_at.desc())
        )
        return Decimal(snapshot.value) if snapshot is not None else None

    def _latest_previous_snapshot(
        self,
        *,
        instrument_type: InstrumentType,
        instrument_id: UUID,
        source: str,
        timeframe: str,
        source_bar_end_at: datetime,
    ) -> MarketRegimeSnapshotModel | None:
        return self._session.scalar(
            select(MarketRegimeSnapshotModel)
            .where(
                MarketRegimeSnapshotModel.instrument_type == instrument_type.value,
                MarketRegimeSnapshotModel.instrument_id == instrument_id,
                MarketRegimeSnapshotModel.source == source,
                MarketRegimeSnapshotModel.timeframe == timeframe,
                MarketRegimeSnapshotModel.config_version == self._config.config_version,
                MarketRegimeSnapshotModel.source_bar_end_at < source_bar_end_at,
            )
            .order_by(MarketRegimeSnapshotModel.source_bar_end_at.desc())
        )

    def _prior_candidate_confirmation_count(
        self,
        *,
        candidate: MarketRegime,
        previous_snapshot: MarketRegimeSnapshotModel,
    ) -> int:
        count = 0
        snapshot: MarketRegimeSnapshotModel | None = previous_snapshot
        while snapshot is not None:
            evidence = cast(dict[str, Any], snapshot.evidence)
            if evidence.get("candidate_regime") != candidate.value:
                break
            count += 1
            snapshot = self._latest_previous_snapshot(
                instrument_type=InstrumentType(snapshot.instrument_type),
                instrument_id=snapshot.instrument_id,
                source=snapshot.source,
                timeframe=snapshot.timeframe,
                source_bar_end_at=snapshot.source_bar_end_at,
            )
        return count

    def _no_trade(
        self,
        reason: str,
        *,
        missing: list[str] | None = None,
    ) -> tuple[MarketRegime, Decimal, dict[str, Any]]:
        evidence: dict[str, Any] = {"candidate_reasons": [reason]}
        if missing:
            evidence["missing"] = missing
        return MarketRegime.NO_TRADE, Decimal("0"), evidence

    def _threshold_evidence(self) -> dict[str, str | int]:
        return {
            "confirmation_bars": self._config.confirmation_bars,
            "trend_adx_threshold": str(self._config.trend_adx_threshold),
            "range_adx_threshold": str(self._config.range_adx_threshold),
            "high_volatility_atr_threshold": str(self._config.high_volatility_atr_threshold),
            "low_volatility_atr_threshold": str(self._config.low_volatility_atr_threshold),
            "high_volatility_bb_width_threshold": str(
                self._config.high_volatility_bb_width_threshold
            ),
            "low_volatility_bb_width_threshold": str(
                self._config.low_volatility_bb_width_threshold
            ),
        }


@dataclass(frozen=True)
class _IndicatorLookup:
    values: dict[str, Decimal]
    parameters_hashes: dict[str, str]
    missing: list[str]


def _find_indicator_snapshot(
    snapshots: list[IndicatorSnapshotModel],
    indicator_name: str,
    parameters: dict[str, object],
) -> IndicatorSnapshotModel | None:
    for snapshot in snapshots:
        if snapshot.indicator_name == indicator_name and snapshot.parameters == parameters:
            return snapshot
    return None


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value
