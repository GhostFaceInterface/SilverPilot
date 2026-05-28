import json
import time
from email.utils import parsedate_to_datetime
import re
from dataclasses import dataclass
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Protocol
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from sqlalchemy import desc, select
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
from app.models import CollectorRun, PriceSnapshot, RawFxRate

logger = logging.getLogger(__name__)


class HardAnomalyError(ValueError):
    pass


KUVEYT_PARSER_VERSION = "kuveyt-public-finance-portal-v2"
YAHOO_FINANCE_CHART_PARSER_VERSION = "yahoo-finance-chart-v1"
METALS_DEV_PARSER_VERSION = "metals-dev-silver-spot-v1"
GOLD_API_PARSER_VERSION = "gold-api-xag-usd-v1"
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
class NormalizedGlobalSilverPrice:
    source: str
    symbol: str
    price: Decimal
    currency: str
    unit: str
    observed_at: datetime
    fetched_at: datetime
    raw_payload: str
    parser_version: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    metadata: dict | None = None


class GlobalSilverProviderError(CollectorError):
    def __init__(self, reason_code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details or {}


class GlobalSilverPriceProvider(Protocol):
    source: str
    collector_name: str
    parser_version: str

    def enabled(self, settings: Settings) -> bool: ...

    def fetch(
        self,
        *,
        settings: Settings,
        fetched_at: datetime,
        client: httpx.Client | None,
    ) -> NormalizedGlobalSilverPrice: ...


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
        # Implement a retry loop (3 retries, 5s delay)
        max_retries = 3
        retry_delay = 5
        parsed = None
        raw_payload = None

        for attempt in range(1, max_retries + 1):
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
                break
            except Exception as exc:
                if isinstance(exc, CollectorError):
                    # Structural errors bypass retry and fail immediately
                    raise exc
                if attempt == max_retries:
                    raise exc
                time.sleep(retry_delay)

        # Anomaly Check 1: Swapped price check (Hard Block Gate)
        if parsed.buy_price < parsed.sell_price:
            raise HardAnomalyError(
                f"Kuveyt returned inverted spread: buy_price ({parsed.buy_price}) < sell_price ({parsed.sell_price})"
            )

        # Anomaly Check 2: Spread percent must be between 2% and 25% (Hard Block Gate)
        spread_abs = parsed.buy_price - parsed.sell_price
        mid_val = (parsed.buy_price + parsed.sell_price) / Decimal("2")
        spread_pct = (spread_abs / mid_val) * Decimal("100") if mid_val > 0 else Decimal("0")
        if not (Decimal("2.0") <= spread_pct <= Decimal("25.0")):
            raise HardAnomalyError(f"Kuveyt silver spread percent {spread_pct:.2f}% is outside of safe range [2%, 25%]")

        # Fetch latest USDTRY rate from raw_fx_rates
        latest_fx = db.execute(
            select(RawFxRate)
            .where(RawFxRate.base_currency == "USD", RawFxRate.quote_currency == "TRY")
            .order_by(desc(RawFxRate.fetched_at), desc(RawFxRate.observed_at))
            .limit(1)
        ).scalar_one_or_none()
        if latest_fx is None:
            raise ValueError("No latest USDTRY exchange rate found in raw_fx_rates")
        usd_try = latest_fx.rate
        if usd_try <= 0:
            raise ValueError(f"Invalid USDTRY exchange rate found: {usd_try}")

        # Convert Kuveyt scraped TRY/gram price to USD/oz
        # Formula: usd_price = try_price ÷ USDTRY × 31.1035
        usd_buy = parsed.buy_price / usd_try * Decimal("31.1035")
        usd_sell = parsed.sell_price / usd_try * Decimal("31.1035")
        usd_mid = (usd_buy + usd_sell) / Decimal("2")

        # Anomaly Check 3: Mid price deviation of ±10% against last 5 PriceSnapshots (Soft anomaly -> degraded mode fallback)
        last_snapshots = (
            db.execute(
                select(PriceSnapshot)
                .where(PriceSnapshot.source == "kuveyt-public-silver-page", PriceSnapshot.currency == "USD")
                .order_by(PriceSnapshot.observed_at.desc())
                .limit(5)
            )
            .scalars()
            .all()
        )

        if last_snapshots:
            avg_usd_mid = sum(s.mid_price for s in last_snapshots) / len(last_snapshots)
            deviation = abs(usd_mid - avg_usd_mid) / avg_usd_mid
            if deviation > Decimal("0.10"):
                raise ValueError(
                    f"Kuveyt USD normalized mid price ({usd_mid:.4f}) deviates by {deviation * 100:.2f}% from the 5-run average ({avg_usd_mid:.4f})"
                )

        # Global Cross-Control (Anomaly 4)
        one_hour_ago = fetched_at - timedelta(hours=1)
        latest_yahoo = db.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.source == "yahoo-si-f", PriceSnapshot.observed_at >= one_hour_ago)
            .order_by(PriceSnapshot.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        yahoo_mid = None
        if latest_yahoo is not None:
            yahoo_mid = latest_yahoo.mid_price
        else:
            try:
                provider = YahooXagUsdProvider()
                parsed_yahoo = provider.fetch(settings=settings, fetched_at=fetched_at, client=client)
                if parsed_yahoo.bid is not None and parsed_yahoo.ask is not None:
                    yahoo_mid = (parsed_yahoo.bid + parsed_yahoo.ask) / Decimal("2")
                else:
                    yahoo_mid = parsed_yahoo.price
            except Exception as e:
                logger.warning(f"Failed to fetch Yahoo SI=F for cross-control: {e}")

        deviation_details = {}
        if yahoo_mid is not None and yahoo_mid > 0:
            deviation_pct = abs(usd_mid - yahoo_mid) / yahoo_mid
            if deviation_pct > Decimal("0.05"):
                logger.warning(
                    f"Kuveyt USD normalized mid price ({usd_mid:.4f}) deviates by "
                    f"{deviation_pct * 100:.2f}% from global Yahoo SI=F price ({yahoo_mid:.4f}) (Anomaly 4)"
                )
                deviation_details = {
                    "warning": f"Kuveyt USD mid price deviates by {deviation_pct * 100:.2f}% from global Yahoo SI=F price",
                    "kuveyt_usd_mid": str(usd_mid),
                    "yahoo_usd_mid": str(yahoo_mid),
                    "deviation_pct": float(deviation_pct),
                }

        run, success, snapshot = ingest_bank_price(
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
            usd_buy_price=usd_buy,
            usd_sell_price=usd_sell,
            resolved_source="kuveyt_public_portal",
            is_degraded=False,
        )

        if deviation_details:
            details = dict(run.details_json) if run.details_json else {}
            details.update(deviation_details)
            run.details_json = details
            db.commit()
            db.refresh(run)

        return run, success, snapshot

    except (CollectorError, HardAnomalyError) as exc:
        db.rollback()
        run = record_failed_run(
            db,
            collector_name="kuveyt_public_silver",
            source="kuveyt-public-silver-page",
            error_message=str(exc),
            details_json={
                "parser_version": KUVEYT_PARSER_VERSION,
                "failure_reason_code": "HARD_ANOMALY" if isinstance(exc, HardAnomalyError) else "STRUCTURAL_ERROR",
            },
        )
        return run, False, None

    except Exception as exc:
        db.rollback()
        # Degraded Mode: fallback to Yahoo SI=F
        try:
            error_msg = str(exc)
            provider = YahooXagUsdProvider()
            parsed_yahoo = provider.fetch(settings=settings, fetched_at=fetched_at, client=client)
            yahoo_price = parsed_yahoo.price

            degraded_payload = {
                "error_reason": error_msg,
                "degraded_mode": True,
                "proxy_source": parsed_yahoo.source,
                "proxy_symbol": parsed_yahoo.symbol,
                "proxy_price": str(yahoo_price),
                **(parsed_yahoo.metadata or {}),
            }

            return ingest_bank_price(
                db,
                source="kuveyt-public-silver-page",
                asset_symbol="XAG",
                buy_price=Decimal("0"),
                sell_price=Decimal("0"),
                currency="TRY",
                observed_at=parsed_yahoo.observed_at,
                fetched_at=fetched_at,
                payload=degraded_payload,
                raw_payload=parsed_yahoo.raw_payload,
                parser_version="kuveyt-degraded-yahoo-proxy-v1",
                collector_name="kuveyt_public_silver",
                usd_buy_price=yahoo_price,
                usd_sell_price=yahoo_price,
                resolved_source="yahoo_si_f",
                is_degraded=True,
            )
        except Exception as fallback_exc:
            db.rollback()
            run = record_failed_run(
                db,
                collector_name="kuveyt_public_silver",
                source="kuveyt-public-silver-page",
                error_message=f"Scraper error: {exc} | Proxy fallback error: {fallback_exc}",
                details_json={"parser_version": KUVEYT_PARSER_VERSION},
            )
            return run, False, None


def collect_yahoo_usd_try(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    provider = YahooUsdTryProvider()
    try:
        parsed, raw_payload = provider.fetch(settings=settings, fetched_at=fetched_at, client=client)
        return ingest_fx_rate(
            db,
            source=provider.source,
            base_currency=parsed.base_currency,
            quote_currency=parsed.quote_currency,
            rate=parsed.rate,
            observed_at=parsed.observed_at,
            fetched_at=fetched_at,
            payload=parsed.payload,
            raw_payload=raw_payload,
            parser_version=provider.parser_version,
            collector_name=provider.collector_name,
        )
    except Exception as exc:
        db.rollback()
        run = record_failed_run(
            db,
            collector_name=provider.collector_name,
            source=provider.source,
            error_message=str(exc),
            details_json={"parser_version": provider.parser_version},
        )
        return run, False


def collect_global_xag_usd(
    db: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    settings = settings or get_settings()
    fetched_at = datetime.now(UTC)
    failures = []

    for provider in _global_xag_providers(settings):
        if not provider.enabled(settings):
            failures.append({"source": provider.source, "failure_reason_code": "DISABLED"})
            continue
        try:
            parsed = provider.fetch(settings=settings, fetched_at=fetched_at, client=client)
            run, raw_inserted, snapshot = ingest_global_price(
                db,
                source=parsed.source,
                asset_symbol=parsed.symbol,
                buy_price=parsed.ask or parsed.price,
                sell_price=parsed.bid or parsed.price,
                currency=parsed.currency,
                observed_at=parsed.observed_at,
                fetched_at=parsed.fetched_at,
                payload=_global_price_payload(parsed, selected=True, fallback_failures=failures),
                raw_payload=parsed.raw_payload,
                parser_version=parsed.parser_version,
                collector_name="global_xag_usd",
            )
            run.details_json = {
                **(run.details_json or {}),
                "selected_global_xag_source": parsed.source,
                "fallback_failures": failures,
            }
            db.commit()
            db.refresh(run)
            return run, raw_inserted, snapshot
        except GlobalSilverProviderError as exc:
            db.rollback()
            failure = {
                "source": provider.source,
                "collector_name": provider.collector_name,
                "failure_reason_code": exc.reason_code,
                **exc.details,
            }
            failures.append(failure)
            record_failed_run(
                db,
                collector_name=provider.collector_name,
                source=provider.source,
                error_message=str(exc),
                details_json={"parser_version": provider.parser_version, **failure},
            )
        except Exception as exc:
            db.rollback()
            failure = {
                "source": provider.source,
                "collector_name": provider.collector_name,
                "failure_reason_code": "PARSE_ERROR",
            }
            failures.append(failure)
            record_failed_run(
                db,
                collector_name=provider.collector_name,
                source=provider.source,
                error_message=str(exc),
                details_json={"parser_version": provider.parser_version, **failure},
            )

    run = record_failed_run(
        db,
        collector_name="global_xag_usd",
        source="global-xag-usd-resolver",
        error_message="No configured global XAG/USD provider returned fresh data",
        details_json={"fallback_failures": failures, "failure_reason_code": "NO_PROVIDER_AVAILABLE"},
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


class YahooXagUsdProvider:
    source = "yahoo-si-f"
    collector_name = "yahoo_xag_usd"
    parser_version = YAHOO_FINANCE_CHART_PARSER_VERSION

    def enabled(self, settings: Settings) -> bool:
        return bool(settings.yahoo_chart_base_url)

    def fetch(
        self,
        *,
        settings: Settings,
        fetched_at: datetime,
        client: httpx.Client | None,
    ) -> NormalizedGlobalSilverPrice:
        url = f"{settings.yahoo_chart_base_url.rstrip('/')}/SI=F"
        raw_payload = _fetch_with_retry_yahoo(
            url,
            settings=settings,
            client=client,
            timeout_seconds=settings.yahoo_xag_usd_timeout_seconds,
            retries=settings.yahoo_xag_usd_retries,
            backoff_seconds=settings.yahoo_xag_usd_backoff_seconds,
            source=self.source,
            params={"range": "5d", "interval": "5m"},
        )
        parsed = parse_yahoo_finance_chart_json(
            raw_payload,
            fetched_at=fetched_at,
            expected_symbol="SI=F",
            source=self.source,
            parser_version=self.parser_version,
        )
        _reject_stale_global_quote(parsed.observed_at, fetched_at, settings=settings, source=self.source)
        return parsed


class YahooUsdTryProvider:
    source = "yahoo-usd-try"
    collector_name = "yahoo_usd_try"
    parser_version = YAHOO_FINANCE_CHART_PARSER_VERSION

    def enabled(self, settings: Settings) -> bool:
        return bool(settings.yahoo_chart_base_url)

    def fetch(
        self,
        *,
        settings: Settings,
        fetched_at: datetime,
        client: httpx.Client | None,
    ) -> tuple[ParsedFxRate, str]:
        url = f"{settings.yahoo_chart_base_url.rstrip('/')}/USDTRY=X"
        raw_payload = _fetch_with_retry_yahoo(
            url,
            settings=settings,
            client=client,
            timeout_seconds=settings.yahoo_xag_usd_timeout_seconds,
            retries=settings.yahoo_xag_usd_retries,
            backoff_seconds=settings.yahoo_xag_usd_backoff_seconds,
            source=self.source,
            params={"range": "5d", "interval": "1h"},
        )
        parsed = parse_yahoo_finance_usdtry_chart_json(
            raw_payload,
            fetched_at=fetched_at,
            source=self.source,
            parser_version=self.parser_version,
        )
        return parsed, raw_payload


class MetalsDevSilverProvider:
    source = "metals-dev-silver-spot"
    collector_name = "metals_dev_silver_spot"
    parser_version = METALS_DEV_PARSER_VERSION

    def enabled(self, settings: Settings) -> bool:
        return bool(settings.metals_dev_api_key)

    def fetch(
        self,
        *,
        settings: Settings,
        fetched_at: datetime,
        client: httpx.Client | None,
    ) -> NormalizedGlobalSilverPrice:
        raw_payload = _fetch_with_retry(
            settings.metals_dev_spot_url,
            settings=settings,
            client=client,
            timeout_seconds=settings.metals_dev_timeout_seconds,
            retries=1,
            backoff_seconds=settings.yahoo_xag_usd_backoff_seconds,
            source=self.source,
            params={
                "api_key": settings.metals_dev_api_key,
                "metal": "silver",
                "currency": "USD",
            },
        )
        parsed = parse_metals_dev_silver_spot_json(raw_payload, fetched_at=fetched_at)
        _reject_stale_global_quote(parsed.observed_at, fetched_at, settings=settings, source=self.source)
        return parsed


class GoldApiSilverProvider:
    source = "gold-api-xag-usd"
    collector_name = "gold_api_xag_usd"
    parser_version = GOLD_API_PARSER_VERSION

    def enabled(self, settings: Settings) -> bool:
        return getattr(settings, "gold_api_xag_usd_enabled", True)

    def fetch(
        self,
        *,
        settings: Settings,
        fetched_at: datetime,
        client: httpx.Client | None,
    ) -> NormalizedGlobalSilverPrice:
        url = getattr(settings, "gold_api_xag_usd_url", "https://api.gold-api.com/price/XAG")
        timeout = getattr(settings, "gold_api_xag_usd_timeout_seconds", 10.0)
        raw_payload = _fetch_with_retry(
            url,
            settings=settings,
            client=client,
            timeout_seconds=timeout,
            retries=1,
            backoff_seconds=1.0,
            source=self.source,
        )
        parsed = parse_gold_api_silver_spot_json(
            raw_payload,
            fetched_at=fetched_at,
            source=self.source,
            parser_version=self.parser_version,
        )
        _reject_stale_global_quote(parsed.observed_at, fetched_at, settings=settings, source=self.source)
        return parsed


def parse_yahoo_finance_chart_json(
    raw_payload: str,
    *,
    fetched_at: datetime,
    expected_symbol: str,
    source: str,
    parser_version: str,
) -> NormalizedGlobalSilverPrice:
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} response is not valid JSON") from exc

    chart = body.get("chart") or {}
    error = chart.get("error")
    if error:
        raise GlobalSilverProviderError("HTTP_ERROR", f"{source} returned chart error: {error}")

    result_list = chart.get("result")
    if not isinstance(result_list, list) or not result_list:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} response missing results")

    result = result_list[0]
    meta = result.get("meta") or {}
    symbol = str(meta.get("symbol") or expected_symbol).upper()
    currency = str(meta.get("currency") or "USD").upper()

    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []

    if not quotes or not isinstance(quotes, list):
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} indicators.quote missing")

    quote = quotes[0] or {}
    closes = quote.get("close") or []

    if len(timestamps) != len(closes):
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} timestamps and closes length mismatch")

    # Find the last non-null close price
    idx = len(closes) - 1
    price = None
    observed_timestamp = None
    while idx >= 0:
        if closes[idx] is not None:
            try:
                price = Decimal(str(closes[idx]))
                observed_timestamp = timestamps[idx]
                break
            except (ValueError, InvalidOperation):
                pass
        idx -= 1

    if price is None or observed_timestamp is None:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} returned no valid close prices")

    observed_at = datetime.fromtimestamp(observed_timestamp, tz=UTC)

    # Gather additional metadata fields from the same index if available
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []

    def get_val(arr, i):
        if i < len(arr) and arr[i] is not None:
            return str(arr[i])
        return None

    payload = {
        "symbol": symbol,
        "observed_timestamp": observed_timestamp,
        "open": get_val(opens, idx),
        "high": get_val(highs, idx),
        "low": get_val(lows, idx),
        "close": str(price),
        "volume": get_val(volumes, idx),
        "source_type": "yahoo_chart_api",
        "reliability_tier": "primary_public_api",
    }

    return NormalizedGlobalSilverPrice(
        source=source,
        symbol="XAG",
        price=price,
        currency=currency,
        unit="troy_ounce",
        observed_at=observed_at,
        fetched_at=fetched_at,
        raw_payload=raw_payload,
        parser_version=parser_version,
        metadata=payload,
    )


def parse_yahoo_finance_usdtry_chart_json(
    raw_payload: str,
    *,
    fetched_at: datetime,
    source: str,
    parser_version: str,
) -> ParsedFxRate:
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise CollectorError(f"{source} response is not valid JSON") from exc

    chart = body.get("chart") or {}
    error = chart.get("error")
    if error:
        raise CollectorError(f"{source} returned chart error: {error}")

    result_list = chart.get("result")
    if not isinstance(result_list, list) or not result_list:
        raise CollectorError(f"{source} response missing results")

    result = result_list[0]
    meta = result.get("meta") or {}
    symbol = str(meta.get("symbol") or "USDTRY=X").upper()

    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []

    if not quotes or not isinstance(quotes, list):
        raise CollectorError(f"{source} indicators.quote missing")

    quote = quotes[0] or {}
    closes = quote.get("close") or []

    if len(timestamps) != len(closes):
        raise CollectorError(f"{source} timestamps and closes length mismatch")

    # Find the last non-null close price
    idx = len(closes) - 1
    rate = None
    observed_timestamp = None
    while idx >= 0:
        if closes[idx] is not None:
            try:
                rate = Decimal(str(closes[idx]))
                observed_timestamp = timestamps[idx]
                break
            except (ValueError, InvalidOperation):
                pass
        idx -= 1

    if rate is None or observed_timestamp is None:
        raise CollectorError(f"{source} returned no valid close rates")

    observed_at = datetime.fromtimestamp(observed_timestamp, tz=UTC)

    payload = {
        "symbol": symbol,
        "observed_timestamp": observed_timestamp,
        "rate": str(rate),
        "source_type": "yahoo_chart_api",
        "base_currency": "USD",
        "quote_currency": "TRY",
    }

    return ParsedFxRate(
        base_currency="USD",
        quote_currency="TRY",
        rate=rate,
        observed_at=observed_at,
        payload=payload,
    )


def parse_metals_dev_silver_spot_json(raw_payload: str, *, fetched_at: datetime) -> NormalizedGlobalSilverPrice:
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise GlobalSilverProviderError("PARSE_ERROR", "Metals.Dev response is not valid JSON") from exc
    if body.get("status") not in (None, "success"):
        raise GlobalSilverProviderError("HTTP_ERROR", "Metals.Dev returned failure status")
    rate = body.get("rate")
    if not isinstance(rate, dict):
        raise GlobalSilverProviderError("PARSE_ERROR", "Metals.Dev spot response is missing rate object")
    price = _decimal(str(rate.get("price") or ""), field_name="Metals.Dev price")
    bid = _optional_decimal(rate.get("bid"), field_name="Metals.Dev bid")
    ask = _optional_decimal(rate.get("ask"), field_name="Metals.Dev ask")
    observed_at = _parse_iso_datetime(body.get("timestamp"), field_name="Metals.Dev timestamp")
    return NormalizedGlobalSilverPrice(
        source=MetalsDevSilverProvider.source,
        symbol="XAG",
        price=price,
        currency=str(body.get("currency") or "USD").upper(),
        unit=str(body.get("unit") or "toz"),
        observed_at=observed_at,
        fetched_at=fetched_at,
        raw_payload=raw_payload,
        parser_version=METALS_DEV_PARSER_VERSION,
        bid=bid,
        ask=ask,
        metadata={
            "metal": body.get("metal"),
            "source_type": "free_api_key_json_api",
            "access_tier": "free_api_key_optional",
            "reliability_tier": "approved_optional_fallback",
        },
    )


def parse_gold_api_silver_spot_json(
    raw_payload: str,
    *,
    fetched_at: datetime,
    source: str,
    parser_version: str,
) -> NormalizedGlobalSilverPrice:
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} response is not valid JSON") from exc

    price_val = body.get("price")
    if price_val is None:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} response missing price")

    try:
        price = Decimal(str(price_val))
    except (ValueError, InvalidOperation) as exc:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{source} returned invalid price: {price_val}") from exc

    currency = str(body.get("currency") or "USD").upper()
    symbol = str(body.get("symbol") or "XAG").upper()

    updated_at_str = body.get("updatedAt")
    if updated_at_str:
        try:
            observed_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except ValueError:
            observed_at = fetched_at
    else:
        observed_at = fetched_at

    return NormalizedGlobalSilverPrice(
        source=source,
        symbol=symbol,
        price=price,
        currency=currency,
        unit="oz",
        observed_at=observed_at,
        fetched_at=fetched_at,
        raw_payload=raw_payload,
        parser_version=parser_version,
        bid=price,
        ask=price,
        metadata={
            "source_type": "free_no_auth_json_api",
            "reliability_tier": "approved_free_fallback",
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
    script_urls = re.findall(
        r'<script[^>]+src=["\']([^"\']*magiclick\.core\.min\.js[^"\']*)["\']', page_html, flags=re.IGNORECASE
    )
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


def _fetch_with_retry(
    url: str,
    *,
    settings: Settings,
    client: httpx.Client | None,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    source: str,
    params: dict | None = None,
) -> str:
    headers = {"User-Agent": settings.collector_user_agent, "Accept": "application/json,text/csv,text/plain,*/*"}
    attempts = retries + 1
    last_timeout = False
    for attempt in range(1, attempts + 1):
        try:
            if client is None:
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as owned_client:
                    response = owned_client.get(url, params=params)
            else:
                response = client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout_seconds,
                    follow_redirects=True,
                )
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as exc:
            last_timeout = True
            if attempt >= attempts:
                raise GlobalSilverProviderError(
                    "TIMEOUT",
                    f"{source} request timed out",
                    details={"attempts": attempt, "timeout_seconds": timeout_seconds},
                ) from exc
        except httpx.HTTPStatusError as exc:
            is_transient = exc.response.status_code in (408, 429) or (500 <= exc.response.status_code < 600)
            if attempt >= attempts or not is_transient:
                raise GlobalSilverProviderError(
                    "HTTP_ERROR",
                    f"{source} returned HTTP {exc.response.status_code}",
                    details={"status_code": exc.response.status_code, "attempts": attempt},
                ) from exc
            logger.warning(f"Transient HTTPStatusError {exc.response.status_code} on attempt {attempt}/{attempts} for {source}: {exc}. Retrying...")
        except httpx.RequestError as exc:
            if attempt >= attempts:
                raise GlobalSilverProviderError(
                    "HTTP_ERROR",
                    f"{source} request failed",
                    details={"attempts": attempt},
                ) from exc
            logger.warning(f"RequestError on attempt {attempt}/{attempts} for {source}: {exc}. Retrying...")
        if attempt < attempts and backoff_seconds > 0:
            time.sleep(backoff_seconds * attempt)
    reason = "TIMEOUT" if last_timeout else "HTTP_ERROR"
    raise GlobalSilverProviderError(reason, f"{source} request failed", details={"attempts": attempts})


def _fetch_with_retry_yahoo(
    url: str,
    *,
    settings: Settings,
    client: httpx.Client | None,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    source: str,
    params: dict | None = None,
) -> str:
    # Use realistic browser user agent to avoid Yahoo blocking
    browser_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers = {"User-Agent": browser_user_agent, "Accept": "application/json"}
    attempts = retries + 1
    last_timeout = False
    for attempt in range(1, attempts + 1):
        try:
            if client is None:
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as owned_client:
                    response = owned_client.get(url, params=params)
            else:
                response = client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout_seconds,
                    follow_redirects=True,
                )
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as exc:
            last_timeout = True
            if attempt >= attempts:
                raise GlobalSilverProviderError(
                    "TIMEOUT",
                    f"{source} request timed out",
                    details={"attempts": attempt, "timeout_seconds": timeout_seconds},
                ) from exc
        except httpx.HTTPStatusError as exc:
            is_transient = exc.response.status_code in (408, 429) or (500 <= exc.response.status_code < 600)
            if attempt >= attempts or not is_transient:
                raise GlobalSilverProviderError(
                    "HTTP_ERROR",
                    f"{source} returned HTTP {exc.response.status_code}",
                    details={"status_code": exc.response.status_code, "attempts": attempt},
                ) from exc
            logger.warning(f"Transient HTTPStatusError {exc.response.status_code} on attempt {attempt}/{attempts} for {source}: {exc}. Retrying...")
        except httpx.RequestError as exc:
            if attempt >= attempts:
                raise GlobalSilverProviderError(
                    "HTTP_ERROR",
                    f"{source} request failed",
                    details={"attempts": attempt},
                ) from exc
            logger.warning(f"RequestError on attempt {attempt}/{attempts} for {source}: {exc}. Retrying...")
        if attempt < attempts and backoff_seconds > 0:
            time.sleep(backoff_seconds * attempt)
    reason = "TIMEOUT" if last_timeout else "HTTP_ERROR"
    raise GlobalSilverProviderError(reason, f"{source} request failed", details={"attempts": attempts})


def _global_xag_providers(settings: Settings) -> list[GlobalSilverPriceProvider]:
    available: dict[str, GlobalSilverPriceProvider] = {
        "yahoo-si-f": YahooXagUsdProvider(),
        "yahoo_si_f": YahooXagUsdProvider(),
        "gold-api-xag-usd": GoldApiSilverProvider(),
        "gold_api_xag_usd": GoldApiSilverProvider(),
        "metals-dev": MetalsDevSilverProvider(),
        "metalsdev": MetalsDevSilverProvider(),
    }

    # Safely parse priority sources from settings
    priority_sources = [
        raw_name.strip().lower() for raw_name in settings.global_xag_source_priority.split(",") if raw_name.strip()
    ]

    # Self-healing fallback: Auto-inject gold-api-xag-usd if not present in configuration priority list
    gold_enabled = getattr(settings, "gold_api_xag_usd_enabled", True)
    if gold_enabled and "gold-api-xag-usd" not in priority_sources and "gold_api_xag_usd" not in priority_sources:
        if "yahoo-si-f" in priority_sources:
            idx = priority_sources.index("yahoo-si-f")
            priority_sources.insert(idx + 1, "gold-api-xag-usd")
        elif "yahoo_si_f" in priority_sources:
            idx = priority_sources.index("yahoo_si_f")
            priority_sources.insert(idx + 1, "gold-api-xag-usd")
        else:
            priority_sources.append("gold-api-xag-usd")

    providers = []
    seen = set()
    for name in priority_sources:
        provider = available.get(name)
        if provider is not None and provider.source not in seen:
            providers.append(provider)
            seen.add(provider.source)

    return providers or [YahooXagUsdProvider(), GoldApiSilverProvider(), MetalsDevSilverProvider()]


def _global_price_payload(
    parsed: NormalizedGlobalSilverPrice,
    *,
    selected: bool = False,
    fallback_failures: list[dict] | None = None,
) -> dict:
    return {
        "source": parsed.source,
        "symbol": parsed.symbol,
        "price": str(parsed.price),
        "currency": parsed.currency,
        "unit": parsed.unit,
        "observed_at": parsed.observed_at.isoformat(),
        "fetched_at": parsed.fetched_at.isoformat(),
        "bid": str(parsed.bid) if parsed.bid is not None else None,
        "ask": str(parsed.ask) if parsed.ask is not None else None,
        "raw_payload_hash": payload_hash(parsed.raw_payload),
        "parser_version": parsed.parser_version,
        "selected_global_xag_source": parsed.source if selected else None,
        "fallback_failures": fallback_failures or [],
        "reliability": parsed.metadata or {},
    }


def _reject_stale_global_quote(observed_at: datetime, fetched_at: datetime, *, settings: Settings, source: str) -> None:
    age_seconds = int((_to_utc(fetched_at) - _to_utc(observed_at)).total_seconds())
    freshness_seconds = settings.global_xag_freshness_minutes * 60
    if age_seconds > freshness_seconds:
        raise GlobalSilverProviderError(
            "STALE_DATA",
            f"{source} returned stale XAG/USD data",
            details={"age_seconds": age_seconds, "freshness_minutes": settings.global_xag_freshness_minutes},
        )


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


def _parse_iso_datetime(value: str | None, *, field_name: str) -> datetime:
    if not value:
        raise GlobalSilverProviderError("PARSE_ERROR", f"{field_name} is missing")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GlobalSilverProviderError("PARSE_ERROR", f"Unsupported {field_name} format: {value}") from exc
    return _to_utc(parsed)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    return _decimal(str(value), field_name=field_name)


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


def parse_kuveyt_finance_portal_json_usd_try(
    raw_payload: str,
    *,
    fetched_at: datetime,
    finance_portal_url: str,
) -> ParsedFxRate:
    import json

    try:
        rows = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise CollectorError("Kuveyt financePortal response is not valid JSON") from exc
    if not isinstance(rows, list) or not rows:
        raise CollectorError("Kuveyt financePortal response returned no rows")

    usd_row = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("Title") or "").upper()
        code = str(row.get("CurrencyCode") or "").upper()
        if "USD" in title or "USD" in code:
            usd_row = row
            break

    if not usd_row:
        raise CollectorError("USD row not found in Kuveyt financePortal response")

    try:
        buy_price = Decimal(str(usd_row["BuyRate"]))
        sell_price = Decimal(str(usd_row["SellRate"]))
    except (KeyError, ValueError) as exc:
        raise CollectorError("Kuveyt financePortal USD row missing valid BuyRate/SellRate") from exc

    midpoint = (buy_price + sell_price) / Decimal("2")

    return ParsedFxRate(
        base_currency="USD",
        quote_currency="TRY",
        rate=midpoint,
        observed_at=fetched_at,
        payload={
            "source_type": "official_public_browser_loaded_json",
            "timestamp_semantics": "no source timestamp in response; observed_at uses fetched_at",
            "finance_portal_url": finance_portal_url,
            "buy_price": str(buy_price),
            "sell_price": str(sell_price),
        },
    )


def collect_kuveyt_usd_try(
    db: Session,
    *,
    settings: Settings,
    client: httpx.Client | None = None,
) -> tuple[CollectorRun, bool]:
    from app.collectors.service import ingest_fx_rate, start_collector_run, finish_collector_run

    try:
        try:
            page_html = _fetch_text(settings.kuveyt_silver_url, settings=settings, client=client)
            core_script_url = discover_kuveyt_core_script_url(page_html, base_url=settings.kuveyt_silver_url)
            core_js = _fetch_text(core_script_url, settings=settings, client=client)
            finance_portal_url = parse_kuveyt_finance_portal_endpoint(core_js, base_url=settings.kuveyt_silver_url)
            raw_payload = _fetch_text(finance_portal_url, settings=settings, client=client)
        except Exception as exc:
            run = start_collector_run(
                db,
                collector_name="kuveyt_usd_try",
                source="kuveyt-public-silver-page",
                records_seen=0,
                details_json={},
            )
            finish_collector_run(db, run, status="failed", error_message=str(exc))
            db.commit()
            return run, False

        fetched_at = _to_utc(datetime.now(UTC))
        try:
            parsed = parse_kuveyt_finance_portal_json_usd_try(
                raw_payload,
                fetched_at=fetched_at,
                finance_portal_url=finance_portal_url,
            )
        except Exception as exc:
            run = start_collector_run(
                db,
                collector_name="kuveyt_usd_try",
                source="kuveyt-public-silver-page",
                records_seen=0,
                details_json={},
            )
            finish_collector_run(db, run, status="failed", error_message=str(exc))
            db.commit()
            return run, False

        run, inserted = ingest_fx_rate(
            db,
            source="kuveyt-public-silver-page",
            base_currency=parsed.base_currency,
            quote_currency=parsed.quote_currency,
            rate=parsed.rate,
            observed_at=parsed.observed_at,
            fetched_at=fetched_at,
            payload=parsed.payload,
            raw_payload=raw_payload,
            parser_version=KUVEYT_PARSER_VERSION,
            collector_name="kuveyt_usd_try",
        )
        return run, inserted
    except Exception as exc:
        db.rollback()
        logger.exception(f"Fatal error in collect_kuveyt_usd_try: {exc}")
        run = start_collector_run(
            db,
            collector_name="kuveyt_usd_try",
            source="kuveyt-public-silver-page",
            records_seen=0,
            details_json={},
        )
        finish_collector_run(db, run, status="failed", error_message=str(exc))
        db.commit()
        return run, False
