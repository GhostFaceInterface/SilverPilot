import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from silverpilot.app.domain.clocks import Clock, RealClock
from silverpilot.app.domain.models import BankInstrument, PriceQuote
from silverpilot.app.domain.value_objects import Money
from silverpilot.app.providers.errors import (
    DataQualityError,
    ProviderParseError,
    ProviderUnavailableError,
    StaleDataError,
)

KUVEYT_TURK_SOURCE_NAME = "kuveyt_turk_finance_portal"
KUVEYT_TURK_BASE_URL = "https://www.kuveytturk.com.tr"
KUVEYT_TURK_FINANCE_PORTAL_PATH = "/ck0d84?B83A1EF44DD940F2FEC85646BDB25EA0"
KUVEYT_TURK_FINANCE_PORTAL_URL = f"{KUVEYT_TURK_BASE_URL}{KUVEYT_TURK_FINANCE_PORTAL_PATH}"
_SILVER_GRAM_SYMBOL = "GMS (gr)"
_HTTP_GET = Callable[[str, float], bytes]
_JsonValue = Any


@dataclass(frozen=True)
class KuveytTurkParsedQuote:
    bank_buy_price: Decimal
    bank_sell_price: Decimal
    source_symbol: str
    source_name: str
    source_hash: str
    provider_reported_at: datetime | None = None
    indicative: bool = True


@dataclass(frozen=True)
class ProviderQuoteResult:
    quote: PriceQuote
    source_hash: str
    provider_reported_at: datetime | None
    indicative: bool


class KuveytTurkPriceProvider:
    """Fetches Kuveyt Turk public indicative silver gram/TRY quotes."""

    def __init__(
        self,
        *,
        url: str = KUVEYT_TURK_FINANCE_PORTAL_URL,
        timeout_seconds: float = 10.0,
        freshness_ttl: timedelta = timedelta(minutes=5),
        clock: Clock | None = None,
        http_get: _HTTP_GET | None = None,
    ) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._freshness_ttl = freshness_ttl
        self._clock = clock or RealClock()
        self._http_get = http_get or _default_http_get

    def fetch_quote(self, instrument: BankInstrument) -> PriceQuote:
        return self.fetch_quote_result(instrument).quote

    def fetch_quote_result(self, instrument: BankInstrument) -> ProviderQuoteResult:
        self._validate_supported_instrument(instrument)
        fetched_at = self._clock.now()
        payload = self._fetch_payload()
        parsed = parse_finance_portal_silver_quote(payload)
        observed_at = parsed.provider_reported_at or fetched_at
        validate_freshness(observed_at=observed_at, now=fetched_at, max_age=self._freshness_ttl)

        quote = PriceQuote(
            id=uuid4(),
            bank_instrument_id=instrument.id,
            bank_buy_price=Money(
                amount=parsed.bank_buy_price,
                currency_code=instrument.currency_code,
            ),
            bank_sell_price=Money(
                amount=parsed.bank_sell_price,
                currency_code=instrument.currency_code,
            ),
            observed_at=observed_at,
            fetched_at=fetched_at,
            source=KUVEYT_TURK_SOURCE_NAME,
        )
        return ProviderQuoteResult(
            quote=quote,
            source_hash=parsed.source_hash,
            provider_reported_at=parsed.provider_reported_at,
            indicative=parsed.indicative,
        )

    def _fetch_payload(self) -> bytes:
        try:
            return self._http_get(self._url, self._timeout_seconds)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError("Kuveyt Turk finance portal is unavailable") from exc

    @staticmethod
    def _validate_supported_instrument(instrument: BankInstrument) -> None:
        if (
            instrument.metal_code != "XAG"
            or instrument.unit_code != "GRAM"
            or instrument.currency_code != "TRY"
        ):
            raise DataQualityError("KuveytTurkPriceProvider currently supports only XAG/GRAM/TRY")


def parse_finance_portal_silver_quote(payload: bytes | str) -> KuveytTurkParsedQuote:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    source_hash = sha256(raw).hexdigest()

    try:
        document = json.loads(raw.decode("utf-8"), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderParseError("Kuveyt Turk payload is not valid JSON") from exc

    row = _find_silver_gram_row(document)
    if row is None:
        raise ProviderParseError("Kuveyt Turk silver gram row GMS (gr) was not found")

    buy_price = _parse_provider_decimal(_required_field(row, "BuyRate"))
    sell_price = _parse_provider_decimal(_required_field(row, "SellRate"))
    _validate_buy_sell_prices(buy_price, sell_price)

    return KuveytTurkParsedQuote(
        bank_buy_price=buy_price,
        bank_sell_price=sell_price,
        source_symbol=_source_symbol(row),
        source_name=_source_name(row),
        source_hash=source_hash,
    )


def validate_freshness(*, observed_at: datetime, now: datetime, max_age: timedelta) -> None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise DataQualityError("observed_at must be timezone-aware")
    if now.tzinfo is None or now.utcoffset() is None:
        raise DataQualityError("now must be timezone-aware")
    if observed_at > now:
        raise DataQualityError("observed_at cannot be in the future")
    if now - observed_at > max_age:
        raise StaleDataError("Kuveyt Turk quote is stale")


def _default_http_get(url: str, timeout_seconds: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "SilverPilot/0.1 public-price-feasibility",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return cast(bytes, response.read())


def _find_silver_gram_row(document: _JsonValue) -> Mapping[str, _JsonValue] | None:
    matches: list[Mapping[str, _JsonValue]] = [
        row for row in _iter_mappings(document) if _is_silver_gram_row(row)
    ]
    if len(matches) > 1:
        raise ProviderParseError("Kuveyt Turk payload contains multiple GMS (gr) rows")
    return matches[0] if matches else None


def _iter_mappings(value: _JsonValue) -> Iterable[Mapping[str, _JsonValue]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_mappings(child)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for child in value:
            yield from _iter_mappings(child)


def _is_silver_gram_row(row: Mapping[str, _JsonValue]) -> bool:
    fields = ("Code", "Symbol", "Name", "FullName", "DisplayName", "CurrencyName")
    values = [str(row[field]) for field in fields if field in row and row[field] is not None]
    searchable = " ".join(values).casefold()
    has_gms_gram_symbol = _SILVER_GRAM_SYMBOL.casefold() in searchable
    has_code_and_silver_context = str(row.get("Code", "")).casefold() == "gms" and (
        "gr" in searchable or "gram" in searchable or "gümüş" in searchable or "gumus" in searchable
    )
    return has_gms_gram_symbol or has_code_and_silver_context


def _required_field(row: Mapping[str, _JsonValue], field_name: str) -> _JsonValue:
    value = row.get(field_name)
    if value is None or value == "":
        raise ProviderParseError(f"Kuveyt Turk field {field_name} is missing")
    return value


def _parse_provider_decimal(value: _JsonValue) -> Decimal:
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        parsed = _parse_decimal_string(value)
    else:
        raise ProviderParseError("Kuveyt Turk price field must be string, integer, or Decimal")

    if parsed <= Decimal("0"):
        raise DataQualityError("Kuveyt Turk price must be greater than zero")
    return parsed


def _parse_decimal_string(value: str) -> Decimal:
    cleaned = re.sub(r"[^\d,.\-]", "", value.strip())
    if not cleaned:
        raise ProviderParseError("Kuveyt Turk price field is empty")

    if "," in cleaned and "." in cleaned:
        decimal_separator = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        cleaned = cleaned.replace(thousands_separator, "")
        cleaned = cleaned.replace(decimal_separator, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ProviderParseError("Kuveyt Turk price field is not a valid decimal") from exc


def _validate_buy_sell_prices(buy_price: Decimal, sell_price: Decimal) -> None:
    if sell_price < buy_price:
        raise DataQualityError("Kuveyt Turk sell price cannot be lower than buy price")


def _source_symbol(row: Mapping[str, _JsonValue]) -> str:
    for field in ("Symbol", "Code", "FullName", "DisplayName"):
        value = row.get(field)
        if value:
            return str(value)
    return _SILVER_GRAM_SYMBOL


def _source_name(row: Mapping[str, _JsonValue]) -> str:
    for field in ("Name", "CurrencyName", "FullName", "DisplayName"):
        value = row.get(field)
        if value:
            return str(value)
    return "Gümüş"


def utc_now() -> datetime:
    return datetime.now(UTC)
