"""Structured news event-risk interpretation.

Hermes produces risk context only. Execution authority remains in RiskManager.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import EventRiskSnapshotModel, NewsEventModel, NewsSourceModel

_VALID_DIRECTIONS = frozenset({"bullish", "bearish", "neutral", "mixed", "unknown"})
_VALID_HORIZONS = frozenset({"intraday", "1d", "1w", "1m", "unknown"})
_VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "unknown"})
_VALID_ACTIONS = frozenset({"veto", "reduce_risk", "no_trade", "monitor", "none"})


@dataclass(frozen=True)
class NewsSourceDefinition:
    code: str
    name: str
    category: str
    reliability_score: Decimal
    source_policy: str
    status: str = "active"

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("news source code is required")
        if not self.name.strip():
            raise ValueError("news source name is required")
        if self.reliability_score < Decimal("0") or self.reliability_score > Decimal("1"):
            raise ValueError("news source reliability must be between 0 and 1")
        if not self.source_policy.strip():
            raise ValueError("news source policy is required")


@dataclass(frozen=True)
class NewsEventPayload:
    source_code: str
    published_at: datetime
    fetched_at: datetime
    title: str
    summary: str
    affected_assets: tuple[str, ...]
    event_type: str
    source_event_time: datetime | None = None
    provider_reported_at: datetime | None = None
    url: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.source_code.strip():
            raise ValueError("news event source code is required")
        if self.fetched_at < self.published_at:
            raise ValueError("news event fetched_at cannot be before published_at")
        if not self.title.strip():
            raise ValueError("news event title is required")
        if not self.event_type.strip():
            raise ValueError("news event type is required")

    @property
    def stable_hash(self) -> str:
        if self.content_hash is not None:
            return self.content_hash
        material = "|".join(
            [
                self.source_code,
                self.published_at.isoformat(),
                self.title.strip(),
                self.summary.strip(),
                self.event_type.strip(),
            ]
        )
        return sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventRiskRule:
    name: str
    keywords: tuple[str, ...]
    direction_bias: str
    risk_level: str
    action_recommendation: str
    time_horizon: str
    confidence: Decimal
    default_assets: tuple[str, ...] = ("XAG",)

    def __post_init__(self) -> None:
        _validate_choice("direction_bias", self.direction_bias, _VALID_DIRECTIONS)
        _validate_choice("risk_level", self.risk_level, _VALID_RISK_LEVELS)
        _validate_choice("action_recommendation", self.action_recommendation, _VALID_ACTIONS)
        _validate_choice("time_horizon", self.time_horizon, _VALID_HORIZONS)
        if self.confidence < Decimal("0") or self.confidence > Decimal("1"):
            raise ValueError("event risk rule confidence must be between 0 and 1")

    def matches(self, event: NewsEventPayload) -> bool:
        haystack = f"{event.event_type} {event.title} {event.summary}".casefold()
        return any(keyword.casefold() in haystack for keyword in self.keywords)


@dataclass(frozen=True)
class HermesRiskPolicy:
    schema_version: str = "hermes-risk-v1"
    stale_after: timedelta = timedelta(hours=24)
    default_confidence: Decimal = Decimal("0.35")
    default_time_horizon: str = "unknown"
    default_risk_level: str = "unknown"
    default_action: str = "monitor"
    default_direction: str = "unknown"
    rules: tuple[EventRiskRule, ...] = field(
        default_factory=lambda: (
            EventRiskRule(
                name="central_bank_tightening",
                keywords=("rate hike", "hawkish", "tightening", "policy shock"),
                direction_bias="bearish",
                risk_level="high",
                action_recommendation="no_trade",
                time_horizon="1d",
                confidence=Decimal("0.75"),
            ),
            EventRiskRule(
                name="market_dislocation",
                keywords=("flash crash", "trading halt", "liquidity freeze", "market shock"),
                direction_bias="mixed",
                risk_level="high",
                action_recommendation="veto",
                time_horizon="intraday",
                confidence=Decimal("0.85"),
            ),
            EventRiskRule(
                name="commodity_supply_disruption",
                keywords=("mine disruption", "supply disruption", "export ban"),
                direction_bias="bullish",
                risk_level="medium",
                action_recommendation="reduce_risk",
                time_horizon="1w",
                confidence=Decimal("0.65"),
            ),
        )
    )

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError("Hermes schema version is required")
        if self.stale_after <= timedelta(0):
            raise ValueError("Hermes stale_after must be greater than zero")
        _validate_choice("default_direction", self.default_direction, _VALID_DIRECTIONS)
        _validate_choice("default_time_horizon", self.default_time_horizon, _VALID_HORIZONS)
        _validate_choice("default_risk_level", self.default_risk_level, _VALID_RISK_LEVELS)
        _validate_choice("default_action", self.default_action, _VALID_ACTIONS)


@dataclass(frozen=True)
class EventRiskInterpretation:
    source: str
    published_at: datetime
    fetched_at: datetime
    title: str
    summary: str
    event_type: str
    affected_assets: tuple[str, ...]
    direction_bias: str
    confidence: Decimal
    time_horizon: str
    risk_level: str
    reasoning: str
    action_recommendation: str
    interpreted_at: datetime
    expires_at: datetime
    schema_version: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "title": self.title,
            "summary": self.summary,
            "event_type": self.event_type,
            "affected_assets": list(self.affected_assets),
            "direction_bias": self.direction_bias,
            "confidence": str(self.confidence),
            "time_horizon": self.time_horizon,
            "risk_level": self.risk_level,
            "reasoning": self.reasoning,
            "action_recommendation": self.action_recommendation,
            "interpreted_at": self.interpreted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "schema_version": self.schema_version,
        }


class NewsInterpreter:
    """Converts normalized news into bounded Hermes event-risk JSON."""

    def __init__(self, *, policy: HermesRiskPolicy | None = None) -> None:
        self._policy = policy or HermesRiskPolicy()

    @property
    def schema_version(self) -> str:
        return self._policy.schema_version

    def interpret(
        self,
        *,
        event: NewsEventPayload,
        interpreted_at: datetime,
    ) -> EventRiskInterpretation | None:
        available_at = max(_aware_datetime(event.published_at), _aware_datetime(event.fetched_at))
        interpreted_at = _aware_datetime(interpreted_at)
        if interpreted_at < available_at:
            raise ValueError("news cannot be interpreted before it is available")
        if interpreted_at - available_at > self._policy.stale_after:
            return None

        rule = self._matching_rule(event)
        if rule is not None:
            affected_assets = event.affected_assets or rule.default_assets
        else:
            affected_assets = event.affected_assets
        direction = rule.direction_bias if rule else self._policy.default_direction
        risk_level = rule.risk_level if rule else self._policy.default_risk_level
        action = rule.action_recommendation if rule else self._policy.default_action
        time_horizon = rule.time_horizon if rule else self._policy.default_time_horizon
        confidence = rule.confidence if rule else self._policy.default_confidence
        reasoning = (
            f"Matched Hermes rule {rule.name} from normalized news metadata."
            if rule
            else "No specific Hermes rule matched; event is monitoring context only."
        )
        return EventRiskInterpretation(
            source=event.source_code,
            published_at=_aware_datetime(event.published_at),
            fetched_at=_aware_datetime(event.fetched_at),
            title=event.title,
            summary=event.summary,
            event_type=event.event_type,
            affected_assets=affected_assets,
            direction_bias=direction,
            confidence=confidence,
            time_horizon=time_horizon,
            risk_level=risk_level,
            reasoning=reasoning,
            action_recommendation=action,
            interpreted_at=interpreted_at,
            expires_at=available_at + self._policy.stale_after,
            schema_version=self._policy.schema_version,
        )

    def _matching_rule(self, event: NewsEventPayload) -> EventRiskRule | None:
        for rule in self._policy.rules:
            if rule.matches(event):
                return rule
        return None


class NewsRiskRepository:
    """Persists news sources, normalized events, and Hermes risk snapshots."""

    def __init__(self, *, session: Session, interpreter: NewsInterpreter | None = None) -> None:
        self._session = session
        self._interpreter = interpreter or NewsInterpreter()

    def upsert_source(
        self,
        *,
        source: NewsSourceDefinition,
        stored_at: datetime,
    ) -> NewsSourceModel:
        existing = self._session.scalar(
            select(NewsSourceModel).where(NewsSourceModel.code == source.code)
        )
        values = {
            "name": source.name,
            "category": source.category,
            "reliability_score": source.reliability_score,
            "source_policy": source.source_policy,
            "status": source.status,
        }
        if existing is not None:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = stored_at
            self._session.flush()
            return existing

        model = NewsSourceModel(
            code=source.code,
            created_at=stored_at,
            **values,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def record_event(
        self,
        *,
        event: NewsEventPayload,
        stored_at: datetime,
    ) -> NewsEventModel:
        source = self._session.scalar(
            select(NewsSourceModel).where(NewsSourceModel.code == event.source_code)
        )
        if source is None:
            raise ValueError(f"news source was not found: {event.source_code}")

        existing = self._session.scalar(
            select(NewsEventModel).where(
                NewsEventModel.source_id == source.id,
                NewsEventModel.content_hash == event.stable_hash,
            )
        )
        values = {
            "source_event_time": event.source_event_time,
            "provider_reported_at": event.provider_reported_at,
            "published_at": event.published_at,
            "fetched_at": event.fetched_at,
            "title": event.title,
            "summary": event.summary,
            "url": event.url,
            "affected_assets": list(event.affected_assets),
            "event_type": event.event_type,
        }
        if existing is not None:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = stored_at
            self._session.flush()
            return existing

        model = NewsEventModel(
            source=source,
            content_hash=event.stable_hash,
            created_at=stored_at,
            **values,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def interpret_event(
        self,
        *,
        news_event_id: UUID,
        interpreted_at: datetime,
    ) -> EventRiskSnapshotModel | None:
        event_model = self._session.get(NewsEventModel, news_event_id)
        if event_model is None:
            raise ValueError(f"news event was not found: {news_event_id}")
        interpretation = self._interpreter.interpret(
            event=_payload_from_model(event_model),
            interpreted_at=interpreted_at,
        )
        if interpretation is None:
            return None

        existing = self._session.scalar(
            select(EventRiskSnapshotModel).where(
                EventRiskSnapshotModel.news_event_id == event_model.id,
                EventRiskSnapshotModel.schema_version == interpretation.schema_version,
            )
        )
        values = {
            "source": interpretation.source,
            "event_type": interpretation.event_type,
            "affected_assets": list(interpretation.affected_assets),
            "direction_bias": interpretation.direction_bias,
            "confidence": interpretation.confidence,
            "time_horizon": interpretation.time_horizon,
            "risk_level": interpretation.risk_level,
            "reasoning": interpretation.reasoning,
            "action_recommendation": interpretation.action_recommendation,
            "interpreted_at": interpretation.interpreted_at,
            "expires_at": interpretation.expires_at,
            "payload": interpretation.to_payload(),
        }
        if existing is not None:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = interpreted_at
            self._session.flush()
            return existing

        snapshot = EventRiskSnapshotModel(
            news_event=event_model,
            schema_version=interpretation.schema_version,
            created_at=interpreted_at,
            **values,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot


def _payload_from_model(event: NewsEventModel) -> NewsEventPayload:
    return NewsEventPayload(
        source_code=event.source.code,
        source_event_time=event.source_event_time,
        provider_reported_at=event.provider_reported_at,
        published_at=event.published_at,
        fetched_at=event.fetched_at,
        title=event.title,
        summary=event.summary,
        url=event.url,
        affected_assets=tuple(event.affected_assets),
        event_type=event.event_type,
        content_hash=event.content_hash,
    )


def _validate_choice(field_name: str, value: str, choices: frozenset[str]) -> None:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {allowed}")


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value
