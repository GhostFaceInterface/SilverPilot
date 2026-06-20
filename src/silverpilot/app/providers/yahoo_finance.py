import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from silverpilot.app.domain.clocks import Clock, RealClock
from silverpilot.app.domain.enums import DataQualityStatus, InstrumentType, MarketSessionStatus
from silverpilot.app.domain.models import MarketBar
from silverpilot.app.providers.errors import (
    DataQualityError,
    ProviderParseError,
    ProviderUnavailableError,
)

YAHOO_RESEARCH_SOURCE_NAME = "yahoo_research"
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_HTTP_GET = Callable[[str, float], bytes]
_JsonValue = Any


@dataclass(frozen=True)
class YahooChartMetadata:
    symbol: str
    timezone: str | None
    exchange: str | None
    currency: str | None
    regular_market_time: datetime | None


@dataclass(frozen=True)
class YahooChartParseResult:
    bars: Sequence[MarketBar]
    metadata: YahooChartMetadata
    source_hash: str


class YahooFinanceReferenceProvider:
    """Fetches Yahoo Finance chart bars for research-only reference backfills."""

    def __init__(
        self,
        *,
        instrument_id: UUID,
        source: str = YAHOO_RESEARCH_SOURCE_NAME,
        base_url: str = YAHOO_CHART_BASE_URL,
        timeout_seconds: float = 10.0,
        data_delay_seconds: int,
        ingestion_delay_seconds: int = 60,
        clock: Clock | None = None,
        http_get: _HTTP_GET | None = None,
    ) -> None:
        if data_delay_seconds < 0:
            raise ValueError("data_delay_seconds cannot be negative")
        if ingestion_delay_seconds < 0:
            raise ValueError("ingestion_delay_seconds cannot be negative")
        self._instrument_id = instrument_id
        self._source = source
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._data_delay_seconds = data_delay_seconds
        self._ingestion_delay_seconds = ingestion_delay_seconds
        self._clock = clock or RealClock()
        self._http_get = http_get or _default_http_get

    def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        period: str,
    ) -> Sequence[MarketBar]:
        fetched_at = self._clock.now()
        provider_interval = _provider_interval(timeframe)
        url = _chart_url(
            base_url=self._base_url,
            symbol=symbol,
            period=period,
            interval=provider_interval,
        )
        try:
            payload = self._http_get(url, self._timeout_seconds)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError("Yahoo Finance chart endpoint is unavailable") from exc
        parsed = parse_yahoo_chart_payload(
            payload,
            instrument_id=self._instrument_id,
            source=self._source,
            requested_timeframe=timeframe,
            provider_interval=provider_interval,
            fetched_at=fetched_at,
            data_delay_seconds=self._data_delay_seconds,
            ingestion_delay_seconds=self._ingestion_delay_seconds,
        )
        return parsed.bars


def parse_yahoo_chart_payload(
    payload: bytes | str,
    *,
    instrument_id: UUID,
    source: str,
    requested_timeframe: str,
    provider_interval: str,
    fetched_at: datetime,
    data_delay_seconds: int,
    ingestion_delay_seconds: int,
) -> YahooChartParseResult:
    if data_delay_seconds < 0:
        raise DataQualityError("data_delay_seconds cannot be negative")
    if ingestion_delay_seconds < 0:
        raise DataQualityError("ingestion_delay_seconds cannot be negative")
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise DataQualityError("fetched_at must be timezone-aware")

    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    source_hash = sha256(raw).hexdigest()
    try:
        document = json.loads(raw.decode("utf-8"), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderParseError("Yahoo chart payload is not valid JSON") from exc

    result = _single_chart_result(document)
    timestamps = _required_sequence(result, "timestamp")
    indicators = _required_mapping(result, "indicators")
    quotes = _required_sequence(indicators, "quote")
    if len(quotes) != 1 or not isinstance(quotes[0], Mapping):
        raise ProviderParseError("Yahoo chart payload must contain exactly one quote block")
    quote_block = cast(Mapping[str, _JsonValue], quotes[0])
    adjusted_values = _adjclose_values(indicators)

    raw_bars = _parse_raw_bars(
        timestamps=timestamps,
        quote_block=quote_block,
        adjusted_values=adjusted_values,
        instrument_id=instrument_id,
        source=source,
        timeframe=provider_interval,
        fetched_at=fetched_at,
        data_delay_seconds=data_delay_seconds,
        ingestion_delay_seconds=ingestion_delay_seconds,
    )
    bars = (
        _aggregate_to_4h(raw_bars)
        if requested_timeframe == "4h" and provider_interval == "1h"
        else raw_bars
    )
    if not bars:
        raise ProviderParseError("Yahoo chart payload did not contain usable OHLC bars")

    meta = _metadata(result)
    return YahooChartParseResult(bars=bars, metadata=meta, source_hash=source_hash)


def _parse_raw_bars(
    *,
    timestamps: Sequence[_JsonValue],
    quote_block: Mapping[str, _JsonValue],
    adjusted_values: Sequence[_JsonValue] | None,
    instrument_id: UUID,
    source: str,
    timeframe: str,
    fetched_at: datetime,
    data_delay_seconds: int,
    ingestion_delay_seconds: int,
) -> list[MarketBar]:
    opens = _required_sequence(quote_block, "open")
    highs = _required_sequence(quote_block, "high")
    lows = _required_sequence(quote_block, "low")
    closes = _required_sequence(quote_block, "close")
    volumes = _optional_sequence(quote_block, "volume")
    lengths = {len(timestamps), len(opens), len(highs), len(lows), len(closes)}
    if volumes is not None:
        lengths.add(len(volumes))
    if adjusted_values is not None:
        lengths.add(len(adjusted_values))
    if len(lengths) != 1:
        raise ProviderParseError("Yahoo chart OHLC arrays have mismatched lengths")

    duration = _timeframe_duration(timeframe)
    bars: list[MarketBar] = []
    for index, timestamp_value in enumerate(timestamps):
        if _has_missing_price(opens[index], highs[index], lows[index], closes[index]):
            continue
        bar_start = _timestamp_to_utc(timestamp_value)
        bar_end = bar_start + duration
        delay = timedelta(seconds=data_delay_seconds + ingestion_delay_seconds)
        bars.append(
            MarketBar(
                id=uuid4(),
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=instrument_id,
                source=source,
                timeframe=timeframe,
                open=_decimal_from_provider(opens[index], "open"),
                high=_decimal_from_provider(highs[index], "high"),
                low=_decimal_from_provider(lows[index], "low"),
                close=_decimal_from_provider(closes[index], "close"),
                quote_count=1,
                bar_start_at=bar_start,
                bar_end_at=bar_end,
                provider_reported_at=bar_end,
                fetched_at=fetched_at,
                stored_at=None,
                data_delay_seconds=data_delay_seconds,
                signal_available_at=bar_end + delay,
                adjusted_close=_optional_decimal(adjusted_values, index, "adjclose"),
                volume=_optional_decimal(volumes, index, "volume"),
                data_quality_status=DataQualityStatus.OK,
                session_status=MarketSessionStatus.UNKNOWN,
                is_backfilled=True,
            )
        )
    return bars


def _aggregate_to_4h(raw_bars: Sequence[MarketBar]) -> list[MarketBar]:
    groups: dict[datetime, list[MarketBar]] = {}
    for bar in raw_bars:
        group_hour = (bar.bar_start_at.hour // 4) * 4
        group_start = bar.bar_start_at.replace(hour=group_hour, minute=0, second=0, microsecond=0)
        groups.setdefault(group_start, []).append(bar)

    aggregated: list[MarketBar] = []
    for group_start in sorted(groups):
        group = sorted(groups[group_start], key=lambda item: item.bar_start_at)
        if len(group) < 4:
            continue
        group_end = group_start + timedelta(hours=4)
        highs = [bar.high for bar in group]
        lows = [bar.low for bar in group]
        volumes = [bar.volume for bar in group if bar.volume is not None]
        signal_available_at = max(
            bar.signal_available_at for bar in group if bar.signal_available_at is not None
        )
        aggregated.append(
            MarketBar(
                id=uuid4(),
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=group[0].instrument_id,
                source=group[0].source,
                timeframe="4h",
                open=group[0].open,
                high=max(highs),
                low=min(lows),
                close=group[-1].close,
                quote_count=len(group),
                bar_start_at=group_start,
                bar_end_at=group_end,
                provider_reported_at=group_end,
                fetched_at=max(bar.fetched_at for bar in group if bar.fetched_at is not None),
                stored_at=None,
                data_delay_seconds=group[0].data_delay_seconds,
                signal_available_at=signal_available_at,
                adjusted_close=group[-1].adjusted_close,
                volume=sum(volumes, Decimal("0")) if volumes else None,
                data_quality_status=DataQualityStatus.OK,
                session_status=MarketSessionStatus.UNKNOWN,
                is_backfilled=True,
            )
        )
    return aggregated


def _chart_url(*, base_url: str, symbol: str, period: str, interval: str) -> str:
    query = urlencode(
        {
            "range": period,
            "interval": interval,
            "includePrePost": "false",
            "events": "history",
        }
    )
    return f"{base_url}/{quote(symbol, safe='')}?{query}"


def _provider_interval(timeframe: str) -> str:
    if timeframe == "4h":
        return "1h"
    if timeframe in {"1h", "1d"}:
        return timeframe
    raise ValueError("Yahoo research backfill supports only 1h, 4h, and 1d")


def _timeframe_duration(timeframe: str) -> timedelta:
    if timeframe == "1h":
        return timedelta(hours=1)
    if timeframe == "1d":
        return timedelta(days=1)
    raise ValueError(f"unsupported provider timeframe: {timeframe}")


def _single_chart_result(document: _JsonValue) -> Mapping[str, _JsonValue]:
    if not isinstance(document, Mapping):
        raise ProviderParseError("Yahoo chart payload root is not an object")
    chart = _required_mapping(document, "chart")
    if chart.get("error") is not None:
        raise ProviderParseError("Yahoo chart payload contains an error")
    results = _required_sequence(chart, "result")
    if len(results) != 1 or not isinstance(results[0], Mapping):
        raise ProviderParseError("Yahoo chart payload must contain exactly one result")
    return cast(Mapping[str, _JsonValue], results[0])


def _metadata(result: Mapping[str, _JsonValue]) -> YahooChartMetadata:
    raw_meta = result.get("meta")
    meta = raw_meta if isinstance(raw_meta, Mapping) else {}
    regular_market_time = meta.get("regularMarketTime")
    return YahooChartMetadata(
        symbol=str(meta.get("symbol", "")),
        timezone=str(meta["timezone"]) if meta.get("timezone") is not None else None,
        exchange=str(meta["exchangeName"]) if meta.get("exchangeName") is not None else None,
        currency=str(meta["currency"]) if meta.get("currency") is not None else None,
        regular_market_time=(
            _timestamp_to_utc(regular_market_time) if regular_market_time is not None else None
        ),
    )


def _adjclose_values(indicators: Mapping[str, _JsonValue]) -> Sequence[_JsonValue] | None:
    adjclose = indicators.get("adjclose")
    if adjclose is None:
        return None
    if not isinstance(adjclose, Sequence) or isinstance(adjclose, (str, bytes)) or not adjclose:
        raise ProviderParseError("Yahoo chart adjclose block is invalid")
    first = adjclose[0]
    if not isinstance(first, Mapping):
        raise ProviderParseError("Yahoo chart adjclose block is invalid")
    return _optional_sequence(cast(Mapping[str, _JsonValue], first), "adjclose")


def _required_mapping(document: Mapping[str, _JsonValue], key: str) -> Mapping[str, _JsonValue]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ProviderParseError(f"Yahoo chart payload missing object field: {key}")
    return cast(Mapping[str, _JsonValue], value)


def _required_sequence(document: Mapping[str, _JsonValue], key: str) -> Sequence[_JsonValue]:
    value = document.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProviderParseError(f"Yahoo chart payload missing array field: {key}")
    return cast(Sequence[_JsonValue], value)


def _optional_sequence(
    document: Mapping[str, _JsonValue],
    key: str,
) -> Sequence[_JsonValue] | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProviderParseError(f"Yahoo chart payload field is not an array: {key}")
    return cast(Sequence[_JsonValue], value)


def _has_missing_price(*values: _JsonValue) -> bool:
    return any(value is None for value in values)


def _timestamp_to_utc(value: _JsonValue) -> datetime:
    if not isinstance(value, int | float | Decimal):
        raise ProviderParseError("Yahoo chart timestamp is not numeric")
    return datetime.fromtimestamp(int(value), tz=UTC)


def _optional_decimal(
    values: Sequence[_JsonValue] | None,
    index: int,
    field_name: str,
) -> Decimal | None:
    if values is None or values[index] is None:
        return None
    return _decimal_from_provider(values[index], field_name)


def _decimal_from_provider(value: _JsonValue, field_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ProviderParseError(f"Yahoo chart field is not numeric: {field_name}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderParseError(f"Yahoo chart field is not numeric: {field_name}") from exc
    if parsed < Decimal("0"):
        raise ProviderParseError(f"Yahoo chart field is negative: {field_name}")
    return parsed


def _default_http_get(url: str, timeout_seconds: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json, */*",
            "User-Agent": "SilverPilot/0.1 yahoo-research-backfill",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return cast(bytes, response.read())


def iter_yahoo_research_symbols() -> Iterable[str]:
    yield "SI=F"
    yield "GC=F"
    yield "TRY=X"
