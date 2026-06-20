from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.collectors import (
    DEFAULT_FRESHNESS_TTL,
    PriceCollector,
    PriceQuoteRetentionPolicy,
    QuoteBarBuilder,
    bank_instrument_from_model,
    classify_quote_freshness,
    cli,
    collect_bank_instrument_once,
    persist_provider_quote,
    prune_price_quotes,
)
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
    provider_reported_at: datetime | None = None
    indicative: bool = True


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


class SequenceProvider:
    def __init__(self, results: list[FakeProviderResult]) -> None:
        self._results = results
        self.calls = 0

    def fetch_quote(self, instrument: BankInstrument) -> PriceQuote:
        return self.fetch_quote_result(instrument).quote

    def fetch_quote_result(self, instrument: BankInstrument) -> FakeProviderResult:
        result = self._results[self.calls]
        self.calls += 1
        assert instrument.id == result.quote.bank_instrument_id
        return result


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


def seed_bank_instrument_model(session: Session) -> BankInstrumentModel:
    instrument = seed_bank_instrument(session)
    model = session.get(BankInstrumentModel, instrument.id)
    assert model is not None
    return model


def quote_for(
    instrument: BankInstrument,
    *,
    observed_at: datetime,
    buy: str,
    sell: str,
    fetched_at: datetime | None = None,
) -> PriceQuote:
    return PriceQuote(
        id=uuid4(),
        bank_instrument_id=instrument.id,
        bank_buy_price=Money(amount=buy, currency_code=instrument.currency_code),
        bank_sell_price=Money(amount=sell, currency_code=instrument.currency_code),
        observed_at=observed_at,
        fetched_at=fetched_at or observed_at,
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
        assert quotes[0].provider_reported_at is None
        assert quotes[0].indicative is True
        assert quotes[0].endpoint_status == "ok"
        assert quotes[0].market_session_status == "unknown"
        assert quotes[0].quote_usability == "indicative_only"
        assert provider.calls == 2


def test_persist_provider_quote_keeps_provider_timestamp_nullable(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        provider_reported_at = now() - timedelta(seconds=30)
        provider_result = FakeProviderResult(
            quote=quote_for(
                instrument,
                observed_at=provider_reported_at,
                fetched_at=now(),
                buy="41.10",
                sell="42.20",
            ),
            source_hash="timestamp-fixture-hash",
            provider_reported_at=provider_reported_at,
            indicative=False,
        )

        result = persist_provider_quote(session, provider_result)
        session.commit()

        assert result.quote.provider_reported_at is not None
        assert result.quote.provider_reported_at.replace(tzinfo=UTC) == provider_reported_at
        assert result.quote.indicative is False
        assert result.quote.endpoint_status == "ok"
        assert result.quote.market_session_status == "unknown"
        assert result.quote.quote_usability == "eligible"


def test_persist_provider_quote_classifies_stale_quotes(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        provider_result = FakeProviderResult(
            quote=quote_for(
                instrument,
                observed_at=now() - DEFAULT_FRESHNESS_TTL - timedelta(seconds=1),
                fetched_at=now(),
                buy="41.10",
                sell="42.20",
            ),
            source_hash="stale-fixture-hash",
        )

        result = persist_provider_quote(session, provider_result)
        session.commit()

        assert result.quote.freshness_status == "stale"


def test_classify_quote_freshness_rejects_invalid_ttl(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        quote = quote_for(instrument, observed_at=now(), buy="41.10", sell="42.20")

        with pytest.raises(ValueError, match="freshness_ttl"):
            classify_quote_freshness(quote, freshness_ttl=timedelta(0))


def test_collect_bank_instrument_once_loads_domain_instrument_and_commits(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        provider = FakeProvider(
            FakeProviderResult(
                quote=quote_for(instrument, observed_at=now(), buy="41.10", sell="42.20"),
                source_hash="fixture-hash",
            )
        )

        result = collect_bank_instrument_once(
            session,
            bank_instrument_id=instrument.id,
            provider=provider,
        )

    with Session(engine) as verification_session:
        stored = list(verification_session.scalars(select(PriceQuoteModel)))
        assert result.inserted is True
        assert result.committed is True
        assert len(stored) == 1
        assert stored[0].bank_instrument_id == instrument.id


def test_bank_instrument_from_model_preserves_provider_codes(engine: Engine) -> None:
    with Session(engine) as session:
        model = seed_bank_instrument_model(session)

        instrument = bank_instrument_from_model(model)

        assert instrument.bank_id == model.bank_id
        assert instrument.metal_code == "XAG"
        assert instrument.unit_code == "GRAM"
        assert instrument.currency_code == "TRY"
        assert instrument.active is True


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


def test_quote_bar_builder_ignores_stale_quotes_by_default(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        persist_provider_quote(
            session,
            FakeProviderResult(
                quote=quote_for(
                    instrument,
                    observed_at=now() - DEFAULT_FRESHNESS_TTL - timedelta(seconds=1),
                    fetched_at=now(),
                    buy="41.10",
                    sell="42.20",
                ),
                source_hash="stale-hash",
            ),
        )
        builder = QuoteBarBuilder(session=session)

        with pytest.raises(ValueError, match="without quotes"):
            builder.build_execution_bar(
                bank_instrument_id=instrument.id,
                source="kuveyt_turk_finance_portal",
                timeframe="1h",
                bar_start_at=now() - timedelta(hours=1),
                bar_end_at=now() + timedelta(hours=1),
            )


def test_quote_bar_builder_rejects_empty_freshness_filter(engine: Engine) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        builder = QuoteBarBuilder(session=session)

        with pytest.raises(ValueError, match="freshness_statuses"):
            builder.build_execution_bar(
                bank_instrument_id=instrument.id,
                source="kuveyt_turk_finance_portal",
                timeframe="1h",
                bar_start_at=now(),
                bar_end_at=now() + timedelta(hours=1),
                freshness_statuses=(),
            )


def test_prune_price_quotes_deletes_only_rows_older_than_retention_cutoff(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        instrument = seed_bank_instrument(session)
        old_quote = FakeProviderResult(
            quote=quote_for(
                instrument,
                observed_at=now() - timedelta(days=10),
                fetched_at=now() - timedelta(days=10),
                buy="40.00",
                sell="41.00",
            ),
            source_hash="old-hash",
        )
        retained_quote = FakeProviderResult(
            quote=quote_for(
                instrument,
                observed_at=now() - timedelta(days=1),
                fetched_at=now() - timedelta(days=1),
                buy="41.00",
                sell="42.00",
            ),
            source_hash="retained-hash",
        )
        persist_provider_quote(session, old_quote)
        persist_provider_quote(session, retained_quote)

        result = prune_price_quotes(
            session,
            policy=PriceQuoteRetentionPolicy(retain_for=timedelta(days=7)),
            now=now(),
            commit=True,
        )

    with Session(engine) as verification_session:
        stored = list(verification_session.scalars(select(PriceQuoteModel)))
        assert result.deleted_count == 1
        assert result.cutoff == now() - timedelta(days=7)
        assert len(stored) == 1
        assert stored[0].source_hash == "retained-hash"


def test_retention_policy_rejects_non_positive_windows() -> None:
    policy = PriceQuoteRetentionPolicy(retain_for=timedelta(0))

    with pytest.raises(ValueError, match="retain_for"):
        policy.cutoff(now())


def test_collect_kuveyt_cli_uses_configured_database_and_prints_summary(
    engine: Engine,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "collector.db"
    database_url = f"sqlite+pysqlite:///{db_path}"
    file_engine = create_engine(database_url, future=True)
    Base.metadata.create_all(file_engine)
    with Session(file_engine) as session:
        instrument = seed_bank_instrument(session)
        session.commit()

    provider = FakeProvider(
        FakeProviderResult(
            quote=quote_for(instrument, observed_at=now(), buy="41.10", sell="42.20"),
            source_hash="fixture-hash",
        )
    )
    monkeypatch.setattr(cli, "KuveytTurkPriceProvider", lambda: provider)

    exit_code = cli.main(
        [
            "--bank-instrument-id",
            str(instrument.id),
            "--database-url",
            database_url,
        ]
    )

    output = capsys.readouterr().out
    with Session(file_engine) as session:
        stored = list(session.scalars(select(PriceQuoteModel)))
        assert exit_code == 0
        assert len(stored) == 1
        assert '"inserted": true' in output
        assert '"attempt": 1' in output
        assert f'"bank_instrument_id": "{instrument.id}"' in output


def test_collect_kuveyt_cli_can_run_bounded_repeated_collection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "collector.db"
    database_url = f"sqlite+pysqlite:///{db_path}"
    file_engine = create_engine(database_url, future=True)
    Base.metadata.create_all(file_engine)
    with Session(file_engine) as session:
        instrument = seed_bank_instrument(session)
        session.commit()

    provider = SequenceProvider(
        [
            FakeProviderResult(
                quote=quote_for(instrument, observed_at=now(), buy="41.10", sell="42.20"),
                source_hash="fixture-hash-1",
            ),
            FakeProviderResult(
                quote=quote_for(
                    instrument,
                    observed_at=now() + timedelta(minutes=1),
                    buy="41.20",
                    sell="42.30",
                ),
                source_hash="fixture-hash-2",
            ),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(cli, "KuveytTurkPriceProvider", lambda: provider)
    monkeypatch.setattr(cli, "sleep", sleep_calls.append)

    exit_code = cli.main(
        [
            "--bank-instrument-id",
            str(instrument.id),
            "--database-url",
            database_url,
            "--repeat",
            "2",
            "--interval-seconds",
            "0.25",
        ]
    )

    output_lines = capsys.readouterr().out.strip().splitlines()
    with Session(file_engine) as session:
        stored = list(session.scalars(select(PriceQuoteModel)))
        assert exit_code == 0
        assert len(stored) == 2
        assert len(output_lines) == 2
        assert '"attempt": 1' in output_lines[0]
        assert '"attempt": 2' in output_lines[1]
        assert sleep_calls == [0.25]
