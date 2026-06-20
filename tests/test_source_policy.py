from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from silverpilot.app.core.settings import Settings
from silverpilot.app.domain.enums import (
    DelayPolicy,
    EndpointStatus,
    ExecutionQuoteSelectionPolicy,
    ExecutionSourcePolicy,
    IndicatorSourcePolicy,
    InstrumentType,
    MarketSessionStatus,
    QuoteUsability,
    SourcePurpose,
    SourceRole,
)
from silverpilot.app.domain.value_objects import (
    InstrumentSessionPolicy,
    MarketSessionCalendar,
    SessionDecision,
    SourcePolicy,
)


def test_source_policy_primitives_capture_v1_defaults() -> None:
    policy = SourcePolicy(source_role=SourceRole.REFERENCE_MARKET)

    assert policy.source_role == SourceRole.REFERENCE_MARKET
    assert policy.indicator_source_policy == IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
    assert policy.execution_source_policy == ExecutionSourcePolicy.ACCOUNT_BOUND_BANK_QUOTE


def test_session_decision_is_source_instrument_venue_and_purpose_scoped() -> None:
    instrument_id = uuid4()
    venue_id = uuid4()
    decision = SessionDecision(
        source="kuveyt_turk_finance_portal",
        instrument_type=InstrumentType.EXECUTION,
        instrument_id=instrument_id,
        venue_id=venue_id,
        purpose=SourcePurpose.EXECUTION,
        endpoint_status=EndpointStatus.OK,
        market_session_status=MarketSessionStatus.INDICATIVE_ONLY,
        quote_usability=QuoteUsability.INDICATIVE_ONLY,
        eligible=False,
        reason="public bank quote is indicative until execution parity is verified",
        decided_at=datetime(2026, 6, 20, 9, 0, tzinfo=UTC),
    )

    assert decision.instrument_id == instrument_id
    assert decision.venue_id == venue_id
    assert decision.purpose == SourcePurpose.EXECUTION
    assert decision.eligible is False


def test_session_policy_rejects_empty_source_calendar_and_reason() -> None:
    calendar = MarketSessionCalendar(code="cme-silver", timezone="America/New_York")

    assert calendar.code == "cme-silver"

    with pytest.raises(ValidationError):
        MarketSessionCalendar(code=" ", timezone="UTC")

    with pytest.raises(ValidationError):
        InstrumentSessionPolicy(
            source=" ",
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            calendar=calendar,
        )

    with pytest.raises(ValidationError):
        SessionDecision(
            source="reference-fixture",
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            purpose=SourcePurpose.INDICATOR,
            eligible=False,
            reason=" ",
            decided_at=datetime(2026, 6, 20, 9, 0, tzinfo=UTC),
        )


def test_settings_expose_behavior_neutral_source_policy_fields() -> None:
    settings = Settings(
        runtime_reference_instrument_id="",
        runtime_reference_source="",
        runtime_fx_source="",
        indicator_source_policy="reference_market_first",
        execution_source_policy="account_bound_bank_quote",
    )

    assert settings.runtime_reference_instrument_id is None
    assert settings.runtime_reference_source is None
    assert settings.runtime_fx_source is None
    assert settings.runtime_reference_timeframe == "4h"
    assert settings.indicator_source_policy == IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
    assert settings.execution_source_policy == ExecutionSourcePolicy.ACCOUNT_BOUND_BANK_QUOTE
    assert settings.reference_delay_policy == DelayPolicy.PROVIDER_DELAYED
    assert settings.reference_ingestion_delay_seconds == 60
    assert settings.execution_quote_selection_policy == (
        ExecutionQuoteSelectionPolicy.LATEST_BEFORE_OR_AT_DECISION
    )
    assert settings.max_quote_lag_seconds == 300
