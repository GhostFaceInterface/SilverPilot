from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.collectors import PriceCollector, QuoteBarBuilder, persist_provider_quote
from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    MarketBarModel,
    MetalModel,
    PriceQuoteModel,
    UnitModel,
)
from silverpilot.app.domain.models import BankInstrument, PriceQuote
from silverpilot.app.domain.value_objects import Money


@dataclass(frozen=True)
class FakeProviderResult:
    quote: PriceQuote
    source_hash: str | None


class FakeProvider:
    def __init__(self, result: FakeProviderResult) -> None:
        self._result = result
        self.calls = 0

    def fetch_quote(self, instrument: BankInstrument) -> PriceQuote:
        self.calls += 1
        return self._result.quote

    def fetch_quote_result(self, instrument: BankInstrument) -> FakeProviderResult:
        self.calls += 1
        assert instrument.id == self._result.quote.bank_instrument_id
        return self._result


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def now() -> datetime:
    return datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def seed_bank_instrument(session: Session) -> BankInstrument:
    created_at = now()
    currency = CurrencyModel(
        id=uuid4(),
        code="TRY",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(id=uuid4(), code="GRAM", name="Gram", precision=6, created_at=created_at)
    metal = MetalModel(
        id=uuid4(),
        code="XAG",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    bank = BankModel(
        id=uuid4(),
        code="kuveyt_turk",
        name="Kuveyt Turk",
        country_code="TR",
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
        price_precision=6,
        status="active",
        created_at=created_at,
    )
    session.add(bank_instrument)
    session.flush()
    return BankInstrument(
        id=bank_instrument.id,
        bank_id=bank.id,
        metal_code=metal.code,
        unit_code=unit.code,
        currency_code=currency.code,
        symbol=bank_instrument.symbol,
        min_trade_amount=Money(
            amount=bank_instrument.min_trade_amount,
            currency_code=currency.code,
        ),
        quantity_precision=bank_instrument.quantity_precision,
        price_precision=bank_instrument.price_precision,
    )


def quote_for(
    instrument: BankInstrument,
    *,
    observed_at: datetime,
    buy: str,
    sell: str,
) -> PriceQuote:
    return PriceQuote(
        id=uuid4(),
        bank_instrument_id=instrument.id,
        bank_buy_price=Money(amount=buy, currency_code=instrument.currency_code),
        bank_sell_price=Money(amount=sell, currency_code=instrument.currency_code),
        observed_at=observed_at,
        fetched_at=observed_at,
        source="kuveyt_turk_finance_portal",
    )


def test_price_collector_persists_provider_quote_and_deduplicates(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        provider_result = FakeProviderResult(
            quote=quote_for(instrument, observed_at=now(), buy="41.10", sell="42.20"),
            source_hash="fixture-hash",
        )
        provider = FakeProvider(provider_result)
        collector = PriceCollector(session=session, provider=provider)

        first = collector.collect_once(instrument)
        second = collector.collect_once(instrument)
        session.commit()

        quotes = list(session.scalars(select(PriceQuoteModel)))
        assert first.inserted is True
        assert second.inserted is False
        assert first.quote.id == second.quote.id
        assert len(quotes) == 1
        assert quotes[0].source_hash == "fixture-hash"
        assert quotes[0].freshness_status == "fresh"
        assert provider.calls == 2


def test_quote_bar_builder_builds_and_updates_execution_bar(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        observed = now()
        for offset, buy, sell, source_hash in (
            (0, "40.00", "42.00", "hash-1"),
            (10, "42.00", "44.00", "hash-2"),
            (20, "41.00", "43.00", "hash-3"),
        ):
            persist_provider_quote(
                session,
                FakeProviderResult(
                    quote=quote_for(
                        instrument,
                        observed_at=observed + timedelta(minutes=offset),
                        buy=buy,
                        sell=sell,
                    ),
                    source_hash=source_hash,
                ),
            )

        builder = QuoteBarBuilder(session=session)
        first = builder.build_execution_bar(
            bank_instrument_id=instrument.id,
            source="kuveyt_turk_finance_portal",
            timeframe="1h",
            bar_start_at=observed,
            bar_end_at=observed + timedelta(hours=1),
        )
        second = builder.build_execution_bar(
            bank_instrument_id=instrument.id,
            source="kuveyt_turk_finance_portal",
            timeframe="1h",
            bar_start_at=observed,
            bar_end_at=observed + timedelta(hours=1),
        )
        session.commit()

        bars = list(session.scalars(select(MarketBarModel)))
        assert first.inserted is True
        assert second.inserted is False
        assert len(bars) == 1
        assert bars[0].open == Decimal("41.00000000")
        assert bars[0].high == Decimal("43.00000000")
        assert bars[0].low == Decimal("41.00000000")
        assert bars[0].close == Decimal("42.00000000")
        assert bars[0].quote_count == 3


def test_quote_bar_builder_rejects_empty_windows(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        builder = QuoteBarBuilder(session=session)

        with pytest.raises(ValueError, match="without quotes"):
            builder.build_execution_bar(
                bank_instrument_id=instrument.id,
                source="kuveyt_turk_finance_portal",
                timeframe="1h",
                bar_start_at=now(),
                bar_end_at=now() + timedelta(hours=1),
            )
