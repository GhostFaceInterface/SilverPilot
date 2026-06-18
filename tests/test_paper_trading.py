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
    LedgerEntryModel,
    MetalModel,
    PaperOrderModel,
    PaperTradeModel,
    PositionModel,
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
from silverpilot.app.domain.enums import PaperOrderSide
from silverpilot.app.paper_trading import PaperBroker, PaperCostModel, PaperOrderRequest

BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_paper_broker_buy_posts_trade_position_wallet_and_ledger(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)

        result = PaperBroker(session=session, cost_model=_costs()).execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME,
            )
        )

        wallet = session.get(WalletModel, fixture.wallet_id)
        position = session.scalar(select(PositionModel))
        ledger_entries = list(session.scalars(select(LedgerEntryModel)))
        assert result.inserted is True
        assert result.order.status == "executed"
        assert result.trade.execution_price == Decimal("50.00000000")
        assert result.trade.net_cash_amount == Decimal("500.50000000")
        assert wallet is not None
        assert wallet.available_amount == Decimal("9499.50000000")
        assert position is not None
        assert position.quantity == Decimal("10.00000000")
        assert position.average_cost == Decimal("50.05000000")
        assert sum(entry.amount for entry in ledger_entries) == Decimal("-500.50000000")


def test_paper_broker_sell_reduces_position_and_realizes_pnl(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)
        broker = PaperBroker(session=session, cost_model=_costs())
        broker.execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME,
            )
        )
        sell_decision_id = _add_approved_decision(
            session, fixture=fixture, policy_version="sell-v1"
        )

        sell = broker.execute(
            PaperOrderRequest(
                risk_decision_id=sell_decision_id,
                side=PaperOrderSide.SELL,
                executed_at=BASE_TIME + timedelta(minutes=1),
            )
        )

        wallet = session.get(WalletModel, fixture.wallet_id)
        position = session.scalar(select(PositionModel))
        assert sell.trade.execution_price == Decimal("49.00000000")
        assert sell.trade.net_cash_amount == Decimal("489.51000000")
        assert sell.trade.realized_pnl == Decimal("-10.99000000")
        assert wallet is not None
        assert wallet.available_amount == Decimal("9989.01000000")
        assert position is not None
        assert position.quantity == Decimal("0E-8")
        assert position.realized_pnl == Decimal("-10.99000000")


def test_same_quote_round_trip_loses_money_after_spread_and_costs(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)
        broker = PaperBroker(session=session, cost_model=_costs())
        broker.execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME,
            )
        )
        sell_decision_id = _add_approved_decision(
            session, fixture=fixture, policy_version="sell-v1"
        )
        sell = broker.execute(
            PaperOrderRequest(
                risk_decision_id=sell_decision_id,
                side=PaperOrderSide.SELL,
                executed_at=BASE_TIME + timedelta(minutes=1),
            )
        )

        wallet = session.get(WalletModel, fixture.wallet_id)
        assert wallet is not None
        assert wallet.available_amount < Decimal("10000")
        assert Decimal("10000") - wallet.available_amount == abs(sell.trade.realized_pnl)


def test_paper_broker_rejects_without_approving_risk_decision(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session, decision="reject")

        with pytest.raises(ValueError, match="approving risk decision"):
            PaperBroker(session=session, cost_model=_costs()).execute(
                PaperOrderRequest(
                    risk_decision_id=fixture.risk_decision_id,
                    side=PaperOrderSide.BUY,
                    executed_at=BASE_TIME,
                )
            )

        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None
        assert session.scalar(select(LedgerEntryModel)) is None


def test_paper_broker_rejects_insufficient_cash_without_partial_state(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session, wallet_available=Decimal("100"))

        with pytest.raises(ValueError, match="insufficient cash"):
            PaperBroker(session=session, cost_model=_costs()).execute(
                PaperOrderRequest(
                    risk_decision_id=fixture.risk_decision_id,
                    side=PaperOrderSide.BUY,
                    executed_at=BASE_TIME,
                )
            )

        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None
        assert session.scalar(select(LedgerEntryModel)) is None
        assert session.scalar(select(PositionModel)) is None


def test_paper_broker_rejects_insufficient_position_without_partial_state(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)

        with pytest.raises(ValueError, match="insufficient position"):
            PaperBroker(session=session, cost_model=_costs()).execute(
                PaperOrderRequest(
                    risk_decision_id=fixture.risk_decision_id,
                    side=PaperOrderSide.SELL,
                    executed_at=BASE_TIME,
                )
            )

        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None
        assert session.scalar(select(LedgerEntryModel)) is None


def test_paper_broker_is_idempotent_per_risk_decision(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)
        broker = PaperBroker(session=session, cost_model=_costs())

        first = broker.execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME,
            )
        )
        second = broker.execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME + timedelta(minutes=1),
            )
        )

        assert first.inserted is True
        assert second.inserted is False
        assert second.trade.id == first.trade.id
        assert len(list(session.scalars(select(PaperOrderModel)))) == 1
        assert len(list(session.scalars(select(PaperTradeModel)))) == 1
        assert len(list(session.scalars(select(LedgerEntryModel)))) == 2


def test_ledger_entries_are_append_only(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_fixture(session)
        PaperBroker(session=session, cost_model=_costs()).execute(
            PaperOrderRequest(
                risk_decision_id=fixture.risk_decision_id,
                side=PaperOrderSide.BUY,
                executed_at=BASE_TIME,
            )
        )
        entry = session.scalar(select(LedgerEntryModel))
        assert entry is not None
        entry.amount = Decimal("0")

        with pytest.raises(ValueError, match="append-only"):
            session.flush()


@dataclass(frozen=True)
class _Fixture:
    account_id: UUID
    bank_instrument_id: UUID
    execution_instrument_id: UUID
    quote_id: UUID
    risk_decision_id: UUID
    wallet_id: UUID


def _costs() -> PaperCostModel:
    return PaperCostModel(fee_rate=Decimal("0.001"), tax_rate=Decimal("0"))


def _seed_fixture(
    session: Session,
    *,
    wallet_available: Decimal = Decimal("10000"),
    decision: str = "approve",
) -> _Fixture:
    created_at = BASE_TIME - timedelta(minutes=1)
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{uuid4().hex[:2]}",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(
        id=uuid4(), code=f"G{uuid4().hex[:4]}", name="Gram", precision=6, created_at=created_at
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
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
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
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        status="active",
        created_at=created_at,
    )
    user = UserModel(
        id=uuid4(), email=f"{uuid4().hex[:8]}@example.com", status="active", created_at=created_at
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
    quote = PriceQuoteModel(
        id=uuid4(),
        bank_instrument=bank_instrument,
        bank_buy_price=Decimal("49"),
        bank_sell_price=Decimal("50"),
        observed_at=BASE_TIME,
        fetched_at=BASE_TIME,
        source="kuveyt_turk_finance_portal",
        source_hash="quote-hash",
        freshness_status="fresh",
        created_at=BASE_TIME,
    )
    session.add_all([wallet, quote])
    session.flush()
    risk_decision_id = _add_approved_decision(
        session,
        fixture=_Fixture(
            account_id=account.id,
            bank_instrument_id=bank_instrument.id,
            execution_instrument_id=execution_instrument.id,
            quote_id=quote.id,
            risk_decision_id=uuid4(),
            wallet_id=wallet.id,
        ),
        decision=decision,
    )
    return _Fixture(
        account_id=account.id,
        bank_instrument_id=bank_instrument.id,
        execution_instrument_id=execution_instrument.id,
        quote_id=quote.id,
        risk_decision_id=risk_decision_id,
        wallet_id=wallet.id,
    )


def _add_approved_decision(
    session: Session,
    *,
    fixture: _Fixture,
    policy_version: str = "risk-v1",
    decision: str = "approve",
) -> UUID:
    created_at = BASE_TIME - timedelta(seconds=30)
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": "500"},
        enabled=True,
        created_at=created_at,
    )
    run = StrategyRunModel(
        id=uuid4(),
        strategy=strategy,
        account_id=fixture.account_id,
        instrument_type="execution",
        instrument_id=fixture.execution_instrument_id,
        source="fixture",
        timeframe="1h",
        source_bar_end_at=created_at,
        run_at=created_at,
        input_hash=uuid4().hex,
        status="intent_created",
        evidence={},
        created_at=created_at,
    )
    intent = TradeIntentModel(
        id=uuid4(),
        account_id=fixture.account_id,
        strategy_run=run,
        side="buy",
        cash_amount=Decimal("500"),
        quantity=None,
        signal_time=created_at,
        status="pending_risk",
        rationale="paper_fixture",
        evidence={},
        created_at=created_at,
    )
    risk_decision = RiskDecisionModel(
        id=uuid4(),
        trade_intent=intent,
        execution_instrument_id=fixture.execution_instrument_id,
        quote_id=fixture.quote_id,
        decision=decision,
        requested_cash_amount=Decimal("500"),
        approved_cash_amount=Decimal("500") if decision != "reject" else Decimal("0"),
        approved_quantity=Decimal("10") if decision != "reject" else Decimal("0"),
        policy_version=policy_version,
        reasons=["risk_approved"] if decision != "reject" else ["stale_quote"],
        constraints_applied={},
        evaluated_at=created_at,
        created_at=created_at,
    )
    session.add(risk_decision)
    session.flush()
    return risk_decision.id
