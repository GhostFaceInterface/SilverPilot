import csv
import json
from email.utils import parsedate_to_datetime
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from io import StringIO
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from sqlalchemy.orm import Session

from app.collectors.service import (
    CollectorError,
    ingest_bank_price,
    ingest_event_items,
    ingest_fx_rate,
    ingest_global_price,
    ingest_news_items,
    payload_hash,
    record_failed_run,
)
from app.core.config import Settings, get_settings
from app.models import CollectorRun, PriceSnapshot

KUVEYT_PARSER_VERSION = "kuveyt-public-finance-portal-v2"
STOOQ_PARSER_VERSION = "stooq-xagusd-csv-v1"
TCMB_PARSER_VERSION = "tcmb-today-xml-v1"
FED_RSS_PARSER_VERSION = "fed-rss-v1"
FRED_OBSERVATIONS_PARSER_VERSION = "fred-observations-v1"


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


@dataclass(frozen=True)
class ParsedNewsItem:
    title: str
    url: str
    published_at: datetime | None
    payload: dict


@dataclass(frozen=True)
class ParsedMacroObservation:
    series_id: str
    value: Decimal
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
        page_html = _fetch_text(settings.kuveyt_silver_url, settings=settings, client=client)
        core_script_url = discover_kuveyt_core_script_url(page_html, base_url=settings.kuveyt_silver_url)
        core_js = _fetch_text(core_script_url, settings=settings, client=client)
        finance_portal_url = parse_kuveyt_finance_portal_endpoint(core_js, base_url=settings.kuveyt_silver_url)
        raw_payload = _fetch_text(finance_portal_url, settings=settings, client=client)
        parsed = parse_kuveyt_finance_portal_json(
            raw_payload,
            fetched_at=fetched_at,
            finance_portal_url=finance_portal_url,
        )
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
        db.rollback()
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
        db.rollback()
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
        db.rollback()
        run = record_failed_run(
            db,
            collector_name="tcmb_usd_try",
            source="tcmb-today-xml",
            error_message=str(exc),
            details_json={"parser_version": TCMB_PARSER_VERSION},
        )
        return run, False


def collect_fed_rss(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, int]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    if not settings.fed_rss_enabled:
        run = record_failed_run(
            db,
            collector_name="fed_rss",
            source="federal-reserve-rss",
            error_message="Fed RSS collector is disabled by configuration",
            details_json={"parser_version": FED_RSS_PARSER_VERSION},
        )
        return run, 0
    try:
        raw_payload = _fetch_text(settings.fed_rss_url, settings=settings, client=client)
        parsed_items = parse_fed_rss(raw_payload)
        run, inserted = ingest_news_items(
            db,
            collector_name="fed_rss",
            source="federal-reserve-rss",
            items=[
                {
                    "title": item.title,
                    "url": item.url,
                    "published_at": item.published_at,
                    **item.payload,
                }
                for item in parsed_items
            ],
            fetched_at=fetched_at,
            raw_payload=raw_payload,
            parser_version=FED_RSS_PARSER_VERSION,
        )
        return run, inserted
    except Exception as exc:
        db.rollback()
        run = record_failed_run(
            db,
            collector_name="fed_rss",
            source="federal-reserve-rss",
            error_message=str(exc),
            details_json={"parser_version": FED_RSS_PARSER_VERSION},
        )
        return run, 0


def collect_fred_macro(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, int]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    series_ids = _fred_series_ids(settings.fred_series_ids)
    if not settings.fred_api_key:
        run = record_failed_run(
            db,
            collector_name="fred_macro",
            source="fred-api",
            error_message="FRED API key is not configured",
            details_json={"parser_version": FRED_OBSERVATIONS_PARSER_VERSION, "series_ids": series_ids},
        )
        return run, 0
    try:
        observations = []
        raw_hash_inputs = []
        for series_id in series_ids:
            raw_payload = _fetch_fred_observations(series_id, settings=settings, client=client)
            raw_hash_inputs.append(raw_payload)
            observations.append(parse_fred_observations(raw_payload, series_id=series_id))

        run, inserted = ingest_event_items(
            db,
            collector_name="fred_macro",
            source="fred-api",
            event_type="fred_macro_observation",
            items=[
                {
                    "series_id": observation.series_id,
                    "value": str(observation.value),
                    "observed_at": observation.observed_at,
                    **observation.payload,
                }
                for observation in observations
            ],
            fetched_at=fetched_at,
            parser_version=FRED_OBSERVATIONS_PARSER_VERSION,
        )
        run.details_json = {
            **(run.details_json or {}),
            "series_ids": series_ids,
            "raw_payload_hashes": [payload_hash(raw_payload) for raw_payload in raw_hash_inputs],
        }
        db.commit()
        db.refresh(run)
        return run, inserted
    except Exception as exc:
        db.rollback()
        run = record_failed_run(
            db,
            collector_name="fred_macro",
            source="fred-api",
            error_message=str(exc),
            details_json={"parser_version": FRED_OBSERVATIONS_PARSER_VERSION, "series_ids": series_ids},
        )
        return run, 0


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


def parse_fed_rss(raw_payload: str) -> list[ParsedNewsItem]:
    root = ElementTree.fromstring(raw_payload)
    channel = root.find("channel")
    if channel is None:
        raise CollectorError("Fed RSS channel is missing")

    items = []
    for item in channel.findall("item"):
        title = _element_text(item, "title").strip()
        link = _element_text(item, "link").strip()
        published_at = _parse_rss_datetime(_optional_element_text(item, "pubDate"))
        guid = _optional_element_text(item, "guid")
        description = _optional_element_text(item, "description")
        categories = [category.text.strip() for category in item.findall("category") if category.text]
        items.append(
            ParsedNewsItem(
                title=title,
                url=link,
                published_at=published_at,
                payload={
                    "guid": guid,
                    "description": description,
                    "categories": categories,
                    "source_type": "official_rss",
                },
            )
        )
    if not items:
        raise CollectorError("Fed RSS feed returned no items")
    return items


def parse_fred_observations(raw_payload: str, *, series_id: str) -> ParsedMacroObservation:
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise CollectorError("FRED observations response is not valid JSON") from exc
    observations = body.get("observations")
    if not isinstance(observations, list) or not observations:
        raise CollectorError(f"FRED returned no observations for {series_id}")

    for observation in observations:
        value = observation.get("value")
        if value in (None, "."):
            continue
        date_value = observation.get("date")
        if not date_value:
            raise CollectorError(f"FRED observation date is missing for {series_id}")
        parsed_value = _decimal(value, field_name=f"{series_id} value")
        return ParsedMacroObservation(
            series_id=series_id,
            value=parsed_value,
            observed_at=_parse_date(date_value, field_name=f"{series_id} date"),
            payload={
                "series_id": series_id,
                "date": date_value,
                "value": str(parsed_value),
                "realtime_start": observation.get("realtime_start"),
                "realtime_end": observation.get("realtime_end"),
                "source_type": "official_api",
                "access_tier": "free_api_key",
                "missing_value_semantics": "dot_values_skipped",
            },
        )
    raise CollectorError(f"FRED returned only missing observations for {series_id}")


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


def discover_kuveyt_core_script_url(page_html: str, *, base_url: str) -> str:
    script_urls = re.findall(r'<script[^>]+src=["\']([^"\']*magiclick\.core\.min\.js[^"\']*)["\']', page_html, flags=re.IGNORECASE)
    if not script_urls:
        raise CollectorError("Kuveyt public page parser could not find public core script")

    # The caller fetches this public browser-loaded script. Keeping discovery separate makes
    # selector/endpoint changes fail visibly instead of silently reusing stale data.
    return urljoin(base_url, script_urls[-1])


def parse_kuveyt_finance_portal_endpoint(core_js: str, *, base_url: str) -> str:
    match = re.search(r'financePortal\s*:\s*"([^"]+)"', core_js)
    if not match:
        raise CollectorError("Kuveyt public core script did not expose financePortal endpoint")
    endpoint = match.group(1)
    if endpoint.startswith(("http://", "https://", "/")):
        return urljoin(base_url, endpoint)
    return urljoin(urljoin(base_url, "/"), endpoint)


def parse_kuveyt_finance_portal_json(
    raw_payload: str,
    *,
    fetched_at: datetime,
    finance_portal_url: str,
) -> ParsedBankPrice:
    try:
        rows = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise CollectorError("Kuveyt financePortal response is not valid JSON") from exc
    if not isinstance(rows, list) or not rows:
        raise CollectorError("Kuveyt financePortal response returned no rows")

    gms_row = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("Title") or "").upper()
        code = str(row.get("CurrencyCode") or "").upper()
        description = str(row.get("CurrencyDescription") or "").lower()
        if "GMS" in title or "GMS" in code or "gümüş" in description or "gumus" in description:
            gms_row = row
            break
    if gms_row is None:
        raise CollectorError("Kuveyt financePortal response did not include GMS silver row")

    bank_buy = _decimal(str(gms_row.get("BuyRate") or ""), field_name="Kuveyt GMS BuyRate")
    bank_sell = _decimal(str(gms_row.get("SellRate") or ""), field_name="Kuveyt GMS SellRate")
    if bank_sell < bank_buy:
        raise CollectorError("Kuveyt financePortal returned inverted silver spread")

    return ParsedBankPrice(
        buy_price=bank_sell,
        sell_price=bank_buy,
        currency="TRY",
        observed_at=fetched_at,
        payload={
            "title": gms_row.get("Title"),
            "currency_code": gms_row.get("CurrencyCode"),
            "currency_description": gms_row.get("CurrencyDescription"),
            "bank_buy_rate": str(bank_buy),
            "bank_sell_rate": str(bank_sell),
            "change_rate": gms_row.get("ChangeRate"),
            "change_rate_negative": gms_row.get("ChangeRateNegative"),
            "label_semantics": "bank BuyRate maps to user sell_price; bank SellRate maps to user buy_price",
            "timestamp_semantics": "no source timestamp in response; observed_at uses fetched_at",
            "source_type": "official_public_browser_loaded_json",
            "stability_risk": "medium",
            "finance_portal_url": finance_portal_url,
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


def _fetch_fred_observations(series_id: str, *, settings: Settings, client: httpx.Client | None) -> str:
    url = f"{settings.fred_api_base_url.rstrip('/')}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": "10",
    }
    headers = {"User-Agent": settings.collector_user_agent}
    try:
        if client is None:
            with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as owned_client:
                response = owned_client.get(url, params=params)
        else:
            response = client.get(url, params=params, headers=headers, timeout=20, follow_redirects=True)
    except httpx.RequestError as exc:
        raise CollectorError(f"FRED API request failed for {series_id}") from exc
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise CollectorError(f"FRED API returned HTTP {exc.response.status_code} for {series_id}") from exc
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


def _parse_date(value: str | None, *, field_name: str) -> datetime:
    if not value:
        raise CollectorError(f"{field_name} is missing")
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CollectorError(f"Unsupported {field_name} format: {value}") from exc


def _element_text(element: ElementTree.Element, child_name: str) -> str:
    child = element.find(child_name)
    if child is None or child.text is None:
        raise CollectorError(f"{child_name} is missing")
    return child.text


def _optional_element_text(element: ElementTree.Element, child_name: str) -> str | None:
    child = element.find(child_name)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _parse_rss_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise CollectorError(f"Unsupported RSS datetime format: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def _fred_series_ids(value: str) -> list[str]:
    series_ids = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not series_ids:
        raise CollectorError("FRED series list is empty")
    return series_ids


def _parse_turkish_decimal(value: str) -> Decimal:
    cleaned = value.strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return _decimal(cleaned, field_name="price")
