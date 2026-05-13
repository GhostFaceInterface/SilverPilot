import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from io import StringIO
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from app.collectors.service import CollectorError, ingest_bank_price, ingest_fx_rate, ingest_global_price, record_failed_run
from app.core.config import Settings, get_settings
from app.models import CollectorRun, PriceSnapshot

KUVEYT_PARSER_VERSION = "kuveyt-public-html-v1"
STOOQ_PARSER_VERSION = "stooq-xagusd-csv-v1"
TCMB_PARSER_VERSION = "tcmb-today-xml-v1"


@dataclass(frozen=True)
class ParsedBankPrice:
    buy_price: Decimal
    sell_price: Decimal
    currency: str
    observed_at: datetime
    payload: dict


@dataclass(frozen=True)
class ParsedGlobalPrice:
    price: Decimal
    currency: str
    observed_at: datetime
    payload: dict


@dataclass(frozen=True)
class ParsedFxRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    observed_at: datetime
    payload: dict


def collect_kuveyt_public_silver(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    try:
        raw_payload = _fetch_text(settings.kuveyt_silver_url, settings=settings, client=client)
        parsed = parse_kuveyt_public_silver_html(raw_payload, fetched_at=fetched_at)
        return ingest_bank_price(
            db,
            source="kuveyt-public-silver-page",
            asset_symbol="XAG",
            buy_price=parsed.buy_price,
            sell_price=parsed.sell_price,
            currency=parsed.currency,
            observed_at=parsed.observed_at,
            fetched_at=fetched_at,
            payload=parsed.payload,
            raw_payload=raw_payload,
            parser_version=KUVEYT_PARSER_VERSION,
            collector_name="kuveyt_public_silver",
        )
    except Exception as exc:
        run = record_failed_run(
            db,
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            error_message=str(exc),
            details_json={"parser_version": KUVEYT_PARSER_VERSION},
        )
        return run, False, None


def collect_stooq_xag_usd(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    try:
        raw_payload = _fetch_text(settings.stooq_xag_usd_url, settings=settings, client=client)
        parsed = parse_stooq_xag_usd_csv(raw_payload)
        return ingest_global_price(
            db,
            source="stooq-xagusd-csv",
            asset_symbol="XAG",
            buy_price=parsed.price,
            sell_price=parsed.price,
            currency=parsed.currency,
            observed_at=parsed.observed_at,
            fetched_at=fetched_at,
            payload=parsed.payload,
            raw_payload=raw_payload,
            parser_version=STOOQ_PARSER_VERSION,
            collector_name="stooq_xag_usd",
        )
    except Exception as exc:
        run = record_failed_run(
            db,
            collector_name="stooq_xag_usd",
            source="stooq-xagusd-csv",
            error_message=str(exc),
            details_json={"parser_version": STOOQ_PARSER_VERSION},
        )
        return run, False, None


def collect_tcmb_usd_try(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    try:
        raw_payload = _fetch_text(settings.tcmb_today_xml_url, settings=settings, client=client)
        parsed = parse_tcmb_usd_try_xml(raw_payload)
        return ingest_fx_rate(
            db,
            source="tcmb-today-xml",
            base_currency=parsed.base_currency,
            quote_currency=parsed.quote_currency,
            rate=parsed.rate,
            observed_at=parsed.observed_at,
            fetched_at=fetched_at,
            payload=parsed.payload,
            raw_payload=raw_payload,
            parser_version=TCMB_PARSER_VERSION,
            collector_name="tcmb_usd_try",
        )
    except Exception as exc:
        run = record_failed_run(
            db,
            collector_name="tcmb_usd_try",
            source="tcmb-today-xml",
            error_message=str(exc),
            details_json={"parser_version": TCMB_PARSER_VERSION},
        )
        return run, False


def parse_stooq_xag_usd_csv(raw_payload: str) -> ParsedGlobalPrice:
    rows = list(csv.DictReader(StringIO(raw_payload.strip())))
    if not rows:
        raise CollectorError("Stooq CSV returned no rows")
    row = rows[0]
    symbol = (row.get("Symbol") or "").upper()
    if symbol != "XAGUSD":
        raise CollectorError(f"Unexpected Stooq symbol: {symbol or 'missing'}")
    close_value = row.get("Close")
    if not close_value or close_value.upper() == "N/D":
        raise CollectorError("Stooq XAG/USD close price is missing")

    observed_at = _parse_datetime(row.get("Date"), row.get("Time"))
    price = _decimal(close_value, field_name="Close")
    return ParsedGlobalPrice(
        price=price,
        currency="USD",
        observed_at=observed_at,
        payload={
            "symbol": symbol,
            "date": row.get("Date"),
            "time": row.get("Time"),
            "open": row.get("Open"),
            "high": row.get("High"),
            "low": row.get("Low"),
            "close": close_value,
            "volume": row.get("Volume"),
            "price_semantics": "close_as_mid; no bid/ask in Stooq CSV",
        },
    )


def parse_tcmb_usd_try_xml(raw_payload: str) -> ParsedFxRate:
    root = ElementTree.fromstring(raw_payload)
    observed_at = _parse_tcmb_date(root.attrib.get("Tarih") or root.attrib.get("Date"))
    for currency in root.findall("Currency"):
        if currency.attrib.get("CurrencyCode") != "USD":
            continue
        buying = _decimal(_element_text(currency, "ForexBuying"), field_name="ForexBuying")
        selling = _decimal(_element_text(currency, "ForexSelling"), field_name="ForexSelling")
        return ParsedFxRate(
            base_currency="USD",
            quote_currency="TRY",
            rate=(buying + selling) / Decimal("2"),
            observed_at=observed_at,
            payload={
                "currency_code": "USD",
                "forex_buying": str(buying),
                "forex_selling": str(selling),
                "rate_semantics": "midpoint_of_tcmb_forex_buying_and_selling",
                "source_date": root.attrib.get("Tarih") or root.attrib.get("Date"),
            },
        )
    raise CollectorError("USD currency row not found in TCMB XML")


def parse_kuveyt_public_silver_html(raw_payload: str, *, fetched_at: datetime) -> ParsedBankPrice:
    text = _html_to_text(raw_payload)
    buy_from_user = _find_price_after_label(
        text,
        labels=(
            "Gümüş Alış",
            "Gram Gümüş Alış",
            "GMS Alış",
            "Gümüş Banka Alış",
        ),
    )
    sell_to_user = _find_price_after_label(
        text,
        labels=(
            "Gümüş Satış",
            "Gram Gümüş Satış",
            "GMS Satış",
            "Gümüş Banka Satış",
        ),
    )
    if buy_from_user is None or sell_to_user is None:
        raise CollectorError("Kuveyt public page parser could not find visible GMS buy/sell prices")
    if sell_to_user < buy_from_user:
        raise CollectorError("Kuveyt public page returned inverted silver spread")

    return ParsedBankPrice(
        buy_price=sell_to_user,
        sell_price=buy_from_user,
        currency="TRY",
        observed_at=fetched_at,
        payload={
            "label_semantics": "bank Alış maps to user sell_price; bank Satış maps to user buy_price",
            "source_type": "public_html",
        },
    )


def _fetch_text(url: str, *, settings: Settings, client: httpx.Client | None) -> str:
    headers = {"User-Agent": settings.collector_user_agent}
    if client is None:
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as owned_client:
            response = owned_client.get(url)
    else:
        response = client.get(url, headers=headers, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _parse_datetime(date_value: str | None, time_value: str | None) -> datetime:
    if not date_value:
        raise CollectorError("Date is missing")
    value = f"{date_value} {time_value or '00:00:00'}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CollectorError(f"Unsupported datetime format: {value}")


def _parse_tcmb_date(value: str | None) -> datetime:
    if not value:
        raise CollectorError("TCMB XML date is missing")
    for fmt in ("%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CollectorError(f"Unsupported TCMB date format: {value}")


def _element_text(element: ElementTree.Element, child_name: str) -> str:
    child = element.find(child_name)
    if child is None or child.text is None:
        raise CollectorError(f"{child_name} is missing")
    return child.text


def _decimal(value: str | None, *, field_name: str) -> Decimal:
    if value is None:
        raise CollectorError(f"{field_name} is missing")
    normalized = value.strip().replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise CollectorError(f"{field_name} is not a valid decimal") from exc
    if result <= 0:
        raise CollectorError(f"{field_name} must be greater than zero")
    return result


def _html_to_text(raw_payload: str) -> str:
    text = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", " ", raw_payload, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _find_price_after_label(text: str, *, labels: tuple[str, ...]) -> Decimal | None:
    for label in labels:
        pattern = rf"{re.escape(label)}(?:\s+Fiyatı)?\s*[:\-]?\s*([0-9][0-9.,]*)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _parse_turkish_decimal(match.group(1))
    return None


def _parse_turkish_decimal(value: str) -> Decimal:
    cleaned = value.strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return _decimal(cleaned, field_name="price")
