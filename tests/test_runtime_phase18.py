from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.core.settings import Settings
from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    InstrumentMappingModel,
    MarketBarModel,
    ReferenceMarketInstrumentModel,
    RuntimeTickModel,
    StrategyRunModel,
    TelegramBotStateModel,
    TradeIntentModel,
    WalletModel,
)
from silverpilot.app.domain.enums import IndicatorSourcePolicy, InstrumentType
from silverpilot.app.domain.models import BankInstrument, PriceQuote
from silverpilot.app.domain.value_objects import Money
from silverpilot.app.main import create_app
from silverpilot.app.providers.yahoo_finance import YAHOO_RESEARCH_SOURCE_NAME
from silverpilot.app.runtime.bootstrap import bootstrap_paper_runtime
from silverpilot.app.runtime.health import SystemHealthService
from silverpilot.app.runtime.paper_loop import PaperRuntime, PaperRuntimeConfig
from silverpilot.app.runtime.telegram_bot import _state


@dataclass(frozen=True)
class FakeProviderResult:
    quote: PriceQuote
    source_hash: str | None = "runtime-fixture"


class FakeProvider:
    def __init__(self, quote: PriceQuote) -> None:
        self._quote = quote

    def fetch_quote(self, instrument: BankInstrument) -> PriceQuote:
        return self._quote

    def fetch_quote_result(self, instrument: BankInstrument) -> FakeProviderResult:
        assert instrument.id == self._quote.bank_instrument_id
        return FakeProviderResult(quote=self._quote)


def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_bootstrap_paper_runtime_is_idempotent_and_preserves_wallet_balance() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        first = bootstrap_paper_runtime(session, now=_time())
        session.commit()
        wallet = session.get(WalletModel, first.wallet_id)
        assert wallet is not None
        wallet.available_amount = Decimal("9000")
        session.commit()

        second = bootstrap_paper_runtime(session, starting_balance=Decimal("20000"), now=_time())
        session.commit()
        wallet = session.get(WalletModel, first.wallet_id)

        assert second.account_id == first.account_id
        assert second.bank_instrument_id == first.bank_instrument_id
        assert second.execution_instrument_id == first.execution_instrument_id
        assert second.strategy_id == first.strategy_id
        assert wallet is not None
        assert wallet.available_amount == Decimal("9000.00000000")


def test_bootstrap_paper_runtime_seeds_yahoo_research_reference_instruments() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        first = bootstrap_paper_runtime(session, now=_time())
        session.commit()

        second = bootstrap_paper_runtime(session, now=_time())
        session.commit()

        references = session.scalars(
            select(ReferenceMarketInstrumentModel)
            .where(ReferenceMarketInstrumentModel.source == YAHOO_RESEARCH_SOURCE_NAME)
            .order_by(ReferenceMarketInstrumentModel.symbol)
        ).all()
        mapping = session.scalar(select(InstrumentMappingModel))

        assert first.yahoo_reference_instrument_ids == second.yahoo_reference_instrument_ids
        assert [reference.symbol for reference in references] == ["GC=F", "SI=F"]
        assert {reference.source_terms_status for reference in references} == {"not_approved"}
        assert {reference.delay_policy for reference in references} == {"manual_review"}
        assert {reference.data_delay_seconds for reference in references} == {None}
        risk_by_symbol = {
            reference.symbol: reference.source_risk_status for reference in references
        }
        assert risk_by_symbol == {
            "GC=F": "not_approved",
            "SI=F": "owner_accepted_paper_use_risk",
        }
        si_reference = next(reference for reference in references if reference.symbol == "SI=F")
        assert si_reference.source_delay_status == "assumed_conservative"
        assert si_reference.approved_by == "owner/manual"
        assert si_reference.approved_scope == "live-paper only"
        assert si_reference.approved_symbols == "SI=F,TRY=X"
        assert si_reference.approved_timeframe == "4h"
        assert si_reference.real_money_allowed is False
        assert mapping is not None
        assert (
            mapping.reference_market_instrument_id == first.yahoo_reference_instrument_ids["SI=F"]
        )
        assert mapping.execution_instrument_id == first.execution_instrument_id
        assert mapping.fx_pair == "USDTRY"


def test_paper_runtime_records_warmup_tick_after_first_closed_bar() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        seeded = bootstrap_paper_runtime(session, now=_time())
        session.commit()

        tick_at = _time() + timedelta(minutes=5)
        quote = PriceQuote(
            id=uuid4(),
            bank_instrument_id=seeded.bank_instrument_id,
            bank_buy_price=Money(amount="49", currency_code="TRY"),
            bank_sell_price=Money(amount="50", currency_code="TRY"),
            observed_at=tick_at - timedelta(minutes=1),
            fetched_at=tick_at - timedelta(minutes=1),
            source="kuveyt_turk_finance_portal",
        )
        runtime = PaperRuntime(
            session=session,
            config=PaperRuntimeConfig(
                account_id=seeded.account_id,
                bank_instrument_id=seeded.bank_instrument_id,
                execution_instrument_id=seeded.execution_instrument_id,
                strategy_id=seeded.strategy_id,
            ),
        )

        result = runtime.tick(now=tick_at, provider=FakeProvider(quote))
        tick = session.scalar(select(RuntimeTickModel))
        warmup = cast(dict[str, object], result.summary["warmup"])

        assert result.status == "warming_up"
        assert session.scalar(select(MarketBarModel)) is not None
        assert warmup["total_bars"] == 1
        assert warmup["eligible_bars"] == 0
        assert warmup["complete"] is False
        assert (
            warmup["indicator_source_policy"] == IndicatorSourcePolicy.REFERENCE_MARKET_FIRST.value
        )
        assert warmup["reason"] == "reference_source_not_configured"
        assert warmup["blocked_by"] == "source_feasibility_gate"
        assert "Approve a reference source" in str(warmup["next_action"])
        assert tick is not None
        assert tick.status == "warming_up"
        assert session.scalar(select(TradeIntentModel)) is None


def test_paper_runtime_can_count_execution_bars_only_in_diagnostic_policy() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        seeded = bootstrap_paper_runtime(session, now=_time())
        session.commit()

        tick_at = _time() + timedelta(minutes=5)
        quote = PriceQuote(
            id=uuid4(),
            bank_instrument_id=seeded.bank_instrument_id,
            bank_buy_price=Money(amount="49", currency_code="TRY"),
            bank_sell_price=Money(amount="50", currency_code="TRY"),
            observed_at=tick_at - timedelta(minutes=1),
            fetched_at=tick_at - timedelta(minutes=1),
            source="kuveyt_turk_finance_portal",
        )
        runtime = PaperRuntime(
            session=session,
            config=PaperRuntimeConfig(
                account_id=seeded.account_id,
                bank_instrument_id=seeded.bank_instrument_id,
                execution_instrument_id=seeded.execution_instrument_id,
                strategy_id=seeded.strategy_id,
                indicator_source_policy=IndicatorSourcePolicy.EXECUTION_BANK_DIAGNOSTIC,
                warmup_bars=2,
            ),
        )

        result = runtime.tick(now=tick_at, provider=FakeProvider(quote))
        warmup = cast(dict[str, object], result.summary["warmup"])

        assert result.status == "warming_up"
        assert warmup["total_bars"] == 1
        assert warmup["eligible_bars"] == 1
        assert warmup["bars"] == 1
        assert warmup["complete"] is False
        assert (
            warmup["indicator_source_policy"]
            == IndicatorSourcePolicy.EXECUTION_BANK_DIAGNOSTIC.value
        )
        assert warmup["reason"] == "insufficient_eligible_bars"
        assert warmup["blocked_by"] == "warmup_data"
        assert warmup["next_action"] == (
            "Collect or backfill 1 more eligible execution bars to finish warm-up."
        )


def test_paper_runtime_uses_latest_signal_available_reference_bar() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        seeded = bootstrap_paper_runtime(session, now=_time())
        reference_instrument_id = seeded.yahoo_reference_instrument_ids["SI=F"]
        available_end_at = _time()
        unavailable_end_at = _time() + timedelta(minutes=5)
        _add_reference_bar(
            session,
            instrument_id=reference_instrument_id,
            bar_end_at=available_end_at,
            signal_available_at=available_end_at + timedelta(minutes=1),
        )
        _add_reference_bar(
            session,
            instrument_id=reference_instrument_id,
            bar_end_at=unavailable_end_at,
            signal_available_at=unavailable_end_at + timedelta(minutes=20),
        )
        session.commit()

        tick_at = _time() + timedelta(minutes=10)
        quote = PriceQuote(
            id=uuid4(),
            bank_instrument_id=seeded.bank_instrument_id,
            bank_buy_price=Money(amount="49", currency_code="TRY"),
            bank_sell_price=Money(amount="50", currency_code="TRY"),
            observed_at=tick_at - timedelta(minutes=1),
            fetched_at=tick_at - timedelta(minutes=1),
            source="kuveyt_turk_finance_portal",
        )
        runtime = PaperRuntime(
            session=session,
            config=PaperRuntimeConfig(
                account_id=seeded.account_id,
                bank_instrument_id=seeded.bank_instrument_id,
                execution_instrument_id=seeded.execution_instrument_id,
                strategy_id=seeded.strategy_id,
                reference_instrument_id=reference_instrument_id,
                reference_source=YAHOO_RESEARCH_SOURCE_NAME,
                reference_timeframe="4h",
                warmup_bars=1,
            ),
        )

        result = runtime.tick(now=tick_at, provider=FakeProvider(quote))
        strategy_run = session.scalar(select(StrategyRunModel))

        assert result.status == "ok"
        assert result.summary["signal_instrument_type"] == InstrumentType.REFERENCE.value
        assert result.summary["signal_instrument_id"] == str(reference_instrument_id)
        assert result.summary["signal_source"] == YAHOO_RESEARCH_SOURCE_NAME
        assert (
            result.summary["signal_bar_end_at"] == available_end_at.replace(tzinfo=None).isoformat()
        )
        assert strategy_run is not None
        assert strategy_run.instrument_type == InstrumentType.REFERENCE.value
        assert strategy_run.instrument_id == reference_instrument_id
        assert strategy_run.source_bar_end_at == available_end_at.replace(tzinfo=None)
        assert session.scalar(select(TradeIntentModel)) is None


def test_system_health_reports_seed_and_warmup_details() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        bootstrap_paper_runtime(session, now=_time())
        session.commit()
        snapshot = SystemHealthService(
            session=session,
            settings=Settings(runtime_enabled=True),
        ).snapshot(now=_time())

    assert snapshot.status == "warming_up"
    assert snapshot.payload["seed_ready"] is True
    assert snapshot.payload["warmup"]["complete"] is False
    assert snapshot.payload["warmup"]["eligible_bars"] == 0
    assert snapshot.payload["warmup"]["total_bars"] == 0
    assert snapshot.payload["warmup"]["reason"] == "reference_source_not_configured"
    assert snapshot.payload["warmup"]["blocked_by"] == "source_feasibility_gate"
    assert "Approve a reference source" in snapshot.payload["warmup"]["next_action"]
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    assert TestClient(app).get("/health").json() == {"status": "ok", "app": "SilverPilot"}


def test_telegram_state_is_read_only_command_surface() -> None:
    db_engine = engine()
    with Session(db_engine) as session:
        state = _state(session, _time())
        state.status = "disabled"
        session.commit()

        stored = session.scalar(select(TelegramBotStateModel))
        assert stored is not None
        assert stored.bot_name == "silverpilot"
        assert stored.status == "disabled"


def _time() -> datetime:
    return datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _add_reference_bar(
    session: Session,
    *,
    instrument_id: UUID,
    bar_end_at: datetime,
    signal_available_at: datetime,
) -> None:
    session.add(
        MarketBarModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=YAHOO_RESEARCH_SOURCE_NAME,
            timeframe="4h",
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            quote_count=1,
            bar_start_at=bar_end_at - timedelta(hours=4),
            bar_end_at=bar_end_at,
            data_delay_seconds=60,
            signal_available_at=signal_available_at,
            data_quality_status="ok",
            session_status="unknown",
            is_backfilled=True,
            created_at=bar_end_at,
        )
    )
