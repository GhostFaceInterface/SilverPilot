from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    InstrumentMappingModel,
    LedgerEntryModel,
    MetalModel,
    PaperOrderModel,
    PaperTradeModel,
    PositionModel,
    PriceQuoteModel,
    ReferenceMarketInstrumentModel,
    RiskDecisionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.risks import EventRiskContext, RiskContext, RiskManager, RiskPolicy

SOURCE = "kuveyt_turk_finance_portal"
BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_risk_manager_approves_valid_intent(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at, cash_amount=Decimal("500"))

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.inserted is True
        assert result.decision.decision == "approve"
        assert result.decision.approved_cash_amount == Decimal("500.00000000")
        assert result.decision.approved_quantity == Decimal("10.00000000")
        assert result.decision.policy_version == "risk-test-v1"
        assert result.decision.reasons == ["risk_approved"]
        assert result.decision.constraints_applied["spread_pct"] == "0.02"


def test_risk_manager_reduces_intent_above_max_order_or_position(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        max_order_fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            cash_amount=Decimal("1500"),
        )

        max_order = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=max_order_fixture.intent_id,
            context=_context(max_order_fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert max_order.decision.decision == "reduce"
        assert max_order.decision.approved_cash_amount == Decimal("1000.00000000")
        assert max_order.decision.reasons == ["reduced:max_order_cash"]

    with Session(engine) as session:
        position_fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            cash_amount=Decimal("800"),
        )

        position = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=position_fixture.intent_id,
            context=_context(
                position_fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                current_position_cash=Decimal("4600"),
            ),
        )

        assert position.decision.decision == "reduce"
        assert position.decision.approved_cash_amount == Decimal("400.00000000")
        assert position.decision.reasons == ["reduced:max_position_cash"]


@pytest.mark.parametrize(
    ("quote_freshness_status", "quote_observed_at", "expected_reason"),
    [
        ("stale", BASE_TIME, "stale_execution_quote"),
        ("fresh", BASE_TIME - timedelta(minutes=6), "stale_execution_quote"),
    ],
)
def test_risk_manager_rejects_stale_quote(
    engine: Engine,
    quote_freshness_status: str,
    quote_observed_at: datetime,
    expected_reason: str,
) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            quote_observed_at=quote_observed_at,
            quote_freshness_status=quote_freshness_status,
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == [expected_reason]


def test_risk_manager_rejects_spread_above_threshold(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            bank_buy_price=Decimal("45"),
            bank_sell_price=Decimal("50"),
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["spread_above_threshold"]


def test_risk_manager_rejects_missing_execution_quote(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                quote_source="missing_source",
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["missing_execution_quote"]


def test_risk_manager_rejects_insufficient_balance(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            cash_amount=Decimal("500"),
            wallet_available=Decimal("300"),
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["insufficient_balance"]


def test_risk_manager_rejects_drawdown_breach(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                current_drawdown=Decimal("0.20"),
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["max_drawdown_breached"]


def test_risk_manager_rejects_missing_required_context(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                current_drawdown=None,
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["missing_risk_context:current_drawdown"]
        assert result.decision.policy_version == "risk-test-v1"


def test_risk_manager_rejects_missing_expected_edge_context(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                expected_edge_after_costs=None,
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["missing_risk_context:expected_edge_after_costs"]


@pytest.mark.parametrize(
    ("fixture_field", "expected_reason"),
    [
        ("allowed_status", "execution_instrument_not_allowed"),
        ("execution_instrument_status", "execution_instrument_inactive"),
        ("bank_instrument_status", "bank_instrument_inactive"),
        ("mapping_status", "missing_reference_execution_mapping"),
    ],
)
def test_risk_manager_rejects_invalid_account_bound_execution(
    engine: Engine,
    fixture_field: str,
    expected_reason: str,
) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture_kwargs = {
            "allowed_status": "active",
            "execution_instrument_status": "active",
            "bank_instrument_status": "active",
            "mapping_status": "active",
        }
        fixture_kwargs[fixture_field] = "inactive"
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            allowed_status=fixture_kwargs["allowed_status"],
            execution_instrument_status=fixture_kwargs["execution_instrument_status"],
            bank_instrument_status=fixture_kwargs["bank_instrument_status"],
            mapping_status=fixture_kwargs["mapping_status"],
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == [expected_reason]


def test_risk_manager_rejects_unknown_execution_instrument_without_fk_write(
    engine: Engine,
) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(uuid4(), evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.execution_instrument_id is None
        assert result.decision.reasons == ["execution_instrument_not_found"]


def test_risk_manager_uses_only_account_bound_quote_not_cheaper_bank(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)
        bound_instrument = session.get(BankInstrumentModel, fixture.bank_instrument_id)
        assert bound_instrument is not None
        cheaper_bank = BankModel(
            id=uuid4(),
            code=f"cheap_{uuid4().hex[:8]}",
            name="Cheaper Bank",
            country_code="TR",
            status="active",
            created_at=evaluated_at,
        )
        cheaper_instrument = BankInstrumentModel(
            id=uuid4(),
            bank=cheaper_bank,
            metal=bound_instrument.metal,
            currency=bound_instrument.currency,
            unit=bound_instrument.unit,
            symbol="CHEAP-XAG-GRAM-TRY",
            min_trade_amount=Decimal("100"),
            quantity_precision=4,
            price_precision=4,
            status="active",
            created_at=evaluated_at,
        )
        session.add(
            PriceQuoteModel(
                id=uuid4(),
                bank_instrument=cheaper_instrument,
                bank_buy_price=Decimal("39"),
                bank_sell_price=Decimal("40"),
                observed_at=evaluated_at,
                fetched_at=evaluated_at,
                source=SOURCE,
                source_hash="cheaper-quote",
                freshness_status="fresh",
                created_at=evaluated_at,
            )
        )
        session.flush()

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "approve"
        assert result.decision.approved_quantity == Decimal("10.00000000")
        assert result.decision.constraints_applied["bank_instrument_id"] == str(
            fixture.bank_instrument_id
        )


def test_risk_manager_applies_bank_quantity_precision(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            cash_amount=Decimal("500"),
            bank_sell_price=Decimal("33.33333333"),
            bank_buy_price=Decimal("32.99999999"),
            quantity_precision=2,
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reduce"
        assert result.decision.reasons == ["reduced:quantity_precision"]
        assert result.decision.approved_quantity == Decimal("15.00000000")
        assert result.decision.approved_cash_amount == Decimal("499.99999995")


def test_risk_manager_rejects_below_bank_min_trade_after_precision(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(
            session,
            evaluated_at=evaluated_at,
            cash_amount=Decimal("150"),
            bank_sell_price=Decimal("100"),
            bank_buy_price=Decimal("99"),
            quantity_precision=0,
            min_trade_amount=Decimal("120"),
        )

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["approved_size_below_bank_min_trade_after_precision"]


def test_risk_manager_rejects_event_risk_no_trade_through_policy(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                event_risk=_event_risk("no_trade", evaluated_at=evaluated_at),
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["event_risk_no_trade"]
        assert result.decision.constraints_applied["event_risk_status"] == "applied"


def test_risk_manager_reduces_event_risk_only_inside_risk_decision(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at, cash_amount=Decimal("800"))

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                event_risk=_event_risk("reduce_risk", evaluated_at=evaluated_at),
            ),
        )

        assert result.decision.decision == "reduce"
        assert result.decision.approved_cash_amount == Decimal("400.00000000")
        assert result.decision.reasons == ["reduced:event_risk"]
        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None


def test_risk_manager_ignores_stale_event_risk(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        result = RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at,
                event_risk=_event_risk(
                    "veto",
                    evaluated_at=evaluated_at - timedelta(days=2),
                ),
            ),
        )

        assert result.decision.decision == "approve"
        assert result.decision.reasons == ["risk_approved"]
        assert result.decision.constraints_applied["event_risk_status"] == "ignored_stale"


def test_risk_manager_is_idempotent_per_intent_and_policy(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)
        manager = RiskManager(session=session, policy=_policy())

        first = manager.evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )
        second = manager.evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.execution_instrument_id,
                evaluated_at=evaluated_at + timedelta(minutes=1),
                current_drawdown=Decimal("0.20"),
            ),
        )

        decisions = list(session.scalars(select(RiskDecisionModel)))
        assert first.inserted is True
        assert second.inserted is False
        assert len(decisions) == 1
        assert decisions[0].decision == "reject"
        assert decisions[0].updated_at == evaluated_at + timedelta(minutes=1)


def test_risk_manager_does_not_create_execution_state(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)

        RiskManager(session=session, policy=_policy()).evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.execution_instrument_id, evaluated_at=evaluated_at),
        )

        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None
        assert session.scalar(select(PositionModel)) is None
        assert session.scalar(select(LedgerEntryModel)) is None


def _policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-test-v1",
        max_order_cash=Decimal("1000"),
        max_position_cash=Decimal("5000"),
        max_daily_loss=Decimal("250"),
        max_drawdown=Decimal("0.10"),
        min_quote_freshness=timedelta(minutes=5),
        max_spread_pct=Decimal("0.03"),
        min_order_cash=Decimal("100"),
    )


def _context(
    execution_instrument_id: UUID,
    *,
    evaluated_at: datetime,
    quote_source: str = SOURCE,
    current_position_cash: Decimal | None = Decimal("0"),
    current_drawdown: Decimal | None = Decimal("0.02"),
    current_daily_loss: Decimal | None = Decimal("0"),
    expected_edge_after_costs: Decimal | None = Decimal("0.05"),
    event_risk: EventRiskContext | None = None,
) -> RiskContext:
    return RiskContext(
        execution_instrument_id=execution_instrument_id,
        quote_source=quote_source,
        evaluated_at=evaluated_at,
        current_position_cash=current_position_cash,
        current_drawdown=current_drawdown,
        current_daily_loss=current_daily_loss,
        expected_edge_after_costs=expected_edge_after_costs,
        event_risk=event_risk,
    )


def _event_risk(action_recommendation: str, *, evaluated_at: datetime) -> EventRiskContext:
    return EventRiskContext(
        snapshot_id=uuid4(),
        action_recommendation=action_recommendation,
        risk_level="high",
        confidence=Decimal("0.85"),
        affected_assets=("XAG",),
        interpreted_at=evaluated_at - timedelta(minutes=1),
        expires_at=evaluated_at + timedelta(hours=1),
        reasoning="test event risk context",
    )


@dataclass(frozen=True)
class _RiskFixture:
    intent_id: UUID
    bank_instrument_id: UUID
    execution_instrument_id: UUID


def _seed_risk_fixture(
    session: Session,
    *,
    evaluated_at: datetime,
    cash_amount: Decimal = Decimal("500"),
    wallet_available: Decimal = Decimal("10000"),
    bank_buy_price: Decimal = Decimal("49"),
    bank_sell_price: Decimal = Decimal("50"),
    min_trade_amount: Decimal = Decimal("100"),
    quantity_precision: int = 4,
    quote_observed_at: datetime | None = None,
    quote_freshness_status: str = "fresh",
    allowed_status: str = "active",
    execution_instrument_status: str = "active",
    bank_instrument_status: str = "active",
    mapping_status: str = "active",
) -> _RiskFixture:
    created_at = evaluated_at - timedelta(minutes=1)
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{uuid4().hex[:2]}",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(
        id=uuid4(),
        code=f"G{uuid4().hex[:4]}",
        name="Gram",
        precision=6,
        created_at=created_at,
    )
    metal = MetalModel(
        id=uuid4(),
        code=f"X{uuid4().hex[:4]}",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    bank = BankModel(
        id=uuid4(),
        code=f"bank_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=created_at,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code=f"venue_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        status="active",
        created_at=created_at,
    )
    bank_instrument = BankInstrumentModel(
        id=uuid4(),
        bank=bank,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol="KT-XAG-GRAM-TRY",
        min_trade_amount=min_trade_amount,
        quantity_precision=quantity_precision,
        price_precision=4,
        status=bank_instrument_status,
        created_at=created_at,
    )
    reference_instrument = ReferenceMarketInstrumentModel(
        id=uuid4(),
        symbol=f"XAGUSD-{uuid4().hex[:6]}",
        source="reference-fixture",
        metal=metal,
        currency=currency,
        unit=unit,
        status="active",
        created_at=created_at,
    )
    execution_instrument = ExecutionInstrumentModel(
        id=uuid4(),
        execution_venue=venue,
        bank_instrument=bank_instrument,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol="KT-XAG-GRAM-TRY",
        status=execution_instrument_status,
        created_at=created_at,
    )
    mapping = InstrumentMappingModel(
        id=uuid4(),
        reference_market_instrument=reference_instrument,
        execution_instrument=execution_instrument,
        status=mapping_status,
        created_at=created_at,
    )
    user = UserModel(
        id=uuid4(),
        email=f"{uuid4().hex[:8]}@example.com",
        status="active",
        created_at=created_at,
    )
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("10000"),
        status="active",
        created_at=created_at,
    )
    wallet = WalletModel(
        id=uuid4(),
        virtual_account=account,
        currency=currency,
        available_amount=wallet_available,
        reserved_amount=Decimal("0"),
        created_at=created_at,
    )
    allowed = VirtualAccountInstrumentModel(
        id=uuid4(),
        virtual_account=account,
        execution_instrument=execution_instrument,
        status=allowed_status,
        created_at=created_at,
    )
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": str(cash_amount)},
        enabled=True,
        created_at=created_at,
    )
    run = StrategyRunModel(
        id=uuid4(),
        strategy=strategy,
        account=account,
        instrument_type="reference",
        instrument_id=reference_instrument.id,
        source="reference-fixture",
        timeframe="1h",
        source_bar_end_at=created_at,
        run_at=created_at,
        input_hash="abc",
        status="intent_created",
        evidence={},
        created_at=created_at,
    )
    intent = TradeIntentModel(
        id=uuid4(),
        account=account,
        strategy_run=run,
        side="buy",
        cash_amount=cash_amount,
        quantity=None,
        signal_time=created_at,
        status="pending_risk",
        rationale="trend_up_pullback_long",
        evidence={},
        created_at=created_at,
    )
    quote = PriceQuoteModel(
        id=uuid4(),
        bank_instrument=bank_instrument,
        bank_buy_price=bank_buy_price,
        bank_sell_price=bank_sell_price,
        observed_at=quote_observed_at or evaluated_at,
        fetched_at=evaluated_at,
        source=SOURCE,
        source_hash="quote-hash",
        freshness_status=quote_freshness_status,
        created_at=evaluated_at,
    )
    session.add_all([wallet, allowed, mapping, intent, quote])
    session.flush()
    return _RiskFixture(
        intent_id=intent.id,
        bank_instrument_id=bank_instrument.id,
        execution_instrument_id=execution_instrument.id,
    )


def _time() -> datetime:
    return BASE_TIME
