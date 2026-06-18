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
    ExecutionVenueModel,
    MetalModel,
    PriceQuoteModel,
    RiskDecisionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.risks import RiskContext, RiskManager, RiskPolicy

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
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
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
            context=_context(max_order_fixture.bank_instrument_id, evaluated_at=evaluated_at),
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
                position_fixture.bank_instrument_id,
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
        ("stale", BASE_TIME, "stale_quote"),
        ("fresh", BASE_TIME - timedelta(minutes=6), "stale_quote"),
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
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
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
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["spread_above_threshold"]


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
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
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
                fixture.bank_instrument_id,
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
                fixture.bank_instrument_id,
                evaluated_at=evaluated_at,
                current_drawdown=None,
            ),
        )

        assert result.decision.decision == "reject"
        assert result.decision.reasons == ["missing_risk_context:current_drawdown"]
        assert result.decision.policy_version == "risk-test-v1"


def test_risk_manager_is_idempotent_per_intent_and_policy(engine: Engine) -> None:
    evaluated_at = _time()
    with Session(engine) as session:
        fixture = _seed_risk_fixture(session, evaluated_at=evaluated_at)
        manager = RiskManager(session=session, policy=_policy())

        first = manager.evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
        )
        second = manager.evaluate(
            trade_intent_id=fixture.intent_id,
            context=_context(
                fixture.bank_instrument_id,
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
            context=_context(fixture.bank_instrument_id, evaluated_at=evaluated_at),
        )

        assert "paper_orders" not in Base.metadata.tables
        assert "paper_trades" not in Base.metadata.tables
        assert "positions" not in Base.metadata.tables
        assert "ledger_entries" not in Base.metadata.tables


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
    bank_instrument_id: UUID,
    *,
    evaluated_at: datetime,
    current_position_cash: Decimal | None = Decimal("0"),
    current_drawdown: Decimal | None = Decimal("0.02"),
    current_daily_loss: Decimal | None = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        bank_instrument_id=bank_instrument_id,
        quote_source=SOURCE,
        evaluated_at=evaluated_at,
        current_position_cash=current_position_cash,
        current_drawdown=current_drawdown,
        current_daily_loss=current_daily_loss,
        expected_edge_after_costs=Decimal("0.05"),
    )


@dataclass(frozen=True)
class _RiskFixture:
    intent_id: UUID
    bank_instrument_id: UUID


def _seed_risk_fixture(
    session: Session,
    *,
    evaluated_at: datetime,
    cash_amount: Decimal = Decimal("500"),
    wallet_available: Decimal = Decimal("10000"),
    bank_buy_price: Decimal = Decimal("49"),
    bank_sell_price: Decimal = Decimal("50"),
    quote_observed_at: datetime | None = None,
    quote_freshness_status: str = "fresh",
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
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
        status="active",
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
        instrument_id=uuid4(),
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
    session.add_all([wallet, intent, quote])
    session.flush()
    return _RiskFixture(intent_id=intent.id, bank_instrument_id=bank_instrument.id)


def _time() -> datetime:
    return BASE_TIME
