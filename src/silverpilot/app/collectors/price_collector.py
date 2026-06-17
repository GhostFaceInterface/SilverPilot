from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import MarketBarModel, PriceQuoteModel
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.domain.interfaces import PriceProvider
from silverpilot.app.domain.models import BankInstrument, PriceQuote

FreshnessStatus = Literal["fresh"]
QuotePriceSide = Literal["bank_buy", "bank_sell", "mid"]


class ProviderQuoteResultLike(Protocol):
    @property
    def quote(self) -> PriceQuote: ...

    @property
    def source_hash(self) -> str | None: ...


@dataclass(frozen=True)
class PriceCollectorResult:
    quote: PriceQuoteModel
    inserted: bool


@dataclass(frozen=True)
class BarBuildResult:
    bar: MarketBarModel
    quote_count: int
    inserted: bool


class PriceCollector:
    """Fetches provider quotes and persists accepted quote candidates."""

    def __init__(self, *, session: Session, provider: PriceProvider) -> None:
        self._session = session
        self._provider = provider

    def collect_once(self, instrument: BankInstrument) -> PriceCollectorResult:
        fetch_quote_result = getattr(self._provider, "fetch_quote_result", None)
        if callable(fetch_quote_result):
            provider_result = fetch_quote_result(instrument)
        else:
            quote = self._provider.fetch_quote(instrument)
            provider_result = _ProviderQuoteResult(quote=quote, source_hash=None)
        return persist_provider_quote(self._session, provider_result)


def persist_provider_quote(
    session: Session,
    provider_result: ProviderQuoteResultLike,
    *,
    freshness_status: FreshnessStatus = "fresh",
) -> PriceCollectorResult:
    quote = provider_result.quote
    existing = session.scalar(
        select(PriceQuoteModel).where(
            PriceQuoteModel.bank_instrument_id == quote.bank_instrument_id,
            PriceQuoteModel.observed_at == quote.observed_at,
            PriceQuoteModel.source == quote.source,
            PriceQuoteModel.source_hash == provider_result.source_hash,
        )
    )
    if existing is not None:
        return PriceCollectorResult(quote=existing, inserted=False)

    model = PriceQuoteModel(
        id=quote.id,
        bank_instrument_id=quote.bank_instrument_id,
        bank_buy_price=quote.bank_buy_price.amount,
        bank_sell_price=quote.bank_sell_price.amount,
        observed_at=quote.observed_at,
        fetched_at=quote.fetched_at,
        source=quote.source,
        source_hash=provider_result.source_hash,
        freshness_status=freshness_status,
        created_at=quote.fetched_at,
    )
    session.add(model)
    session.flush()
    return PriceCollectorResult(quote=model, inserted=True)


class QuoteBarBuilder:
    """Builds deterministic OHLC bars from persisted quote rows."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def build_execution_bar(
        self,
        *,
        bank_instrument_id: UUID,
        source: str,
        timeframe: str,
        bar_start_at: datetime,
        bar_end_at: datetime,
        price_side: QuotePriceSide = "mid",
    ) -> BarBuildResult:
        if bar_start_at >= bar_end_at:
            raise ValueError("bar_start_at must be before bar_end_at")

        quotes = list(
            self._session.scalars(
                select(PriceQuoteModel)
                .where(
                    PriceQuoteModel.bank_instrument_id == bank_instrument_id,
                    PriceQuoteModel.source == source,
                    PriceQuoteModel.observed_at >= bar_start_at,
                    PriceQuoteModel.observed_at < bar_end_at,
                )
                .order_by(PriceQuoteModel.observed_at.asc(), PriceQuoteModel.fetched_at.asc())
            )
        )
        if not quotes:
            raise ValueError("cannot build market bar without quotes")

        prices = [_quote_price(quote, price_side) for quote in quotes]
        existing = self._session.scalar(
            select(MarketBarModel).where(
                MarketBarModel.instrument_type == InstrumentType.EXECUTION.value,
                MarketBarModel.instrument_id == bank_instrument_id,
                MarketBarModel.source == source,
                MarketBarModel.timeframe == timeframe,
                MarketBarModel.bar_start_at == bar_start_at,
            )
        )

        values = {
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "quote_count": len(prices),
            "bar_end_at": bar_end_at,
        }
        if existing is not None:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = bar_end_at
            self._session.flush()
            return BarBuildResult(bar=existing, quote_count=len(prices), inserted=False)

        bar = MarketBarModel(
            instrument_type=InstrumentType.EXECUTION.value,
            instrument_id=bank_instrument_id,
            source=source,
            timeframe=timeframe,
            bar_start_at=bar_start_at,
            created_at=bar_end_at,
            **values,
        )
        self._session.add(bar)
        self._session.flush()
        return BarBuildResult(bar=bar, quote_count=len(prices), inserted=True)


def _quote_price(quote: PriceQuoteModel, price_side: QuotePriceSide) -> Decimal:
    if price_side == "bank_buy":
        return quote.bank_buy_price
    if price_side == "bank_sell":
        return quote.bank_sell_price
    return _mid_price([quote.bank_buy_price, quote.bank_sell_price])


def _mid_price(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


@dataclass(frozen=True)
class _ProviderQuoteResult:
    quote: PriceQuote
    source_hash: str | None
