from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from silverpilot.app.domain.clocks import SimulatedClock
from silverpilot.app.domain.models import BankInstrument
from silverpilot.app.domain.value_objects import Money
from silverpilot.app.providers.errors import (
    DataQualityError,
    ProviderParseError,
    StaleDataError,
)
from silverpilot.app.providers.kuveyt_turk import (
    KUVEYT_TURK_CORE_JS_URL,
    KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL,
    KUVEYT_TURK_SOURCE_NAME,
    KuveytTurkEndpointResolver,
    KuveytTurkPriceProvider,
    parse_finance_portal_silver_quote,
    validate_freshness,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "providers" / "kuveyt_turk_finance_portal.json"
DISCOVERED_PATH = "/ck0d84?B83A1EF44DD940F2FEC85646BDB25EA0"
DISCOVERED_URL = f"https://www.kuveytturk.com.tr{DISCOVERED_PATH}"


def _silver_instrument() -> BankInstrument:
    return BankInstrument(
        id=uuid4(),
        bank_id=uuid4(),
        metal_code="XAG",
        unit_code="GRAM",
        currency_code="TRY",
        symbol="KUVEYT:XAG:GRAM:TRY",
        min_trade_amount=Money(amount="100", currency_code="TRY"),
        quantity_precision=4,
        price_precision=6,
    )


def test_parse_finance_portal_silver_quote_from_sanitized_fixture() -> None:
    parsed = parse_finance_portal_silver_quote(FIXTURE_PATH.read_bytes())

    assert parsed.bank_buy_price == Decimal("41.100000")
    assert parsed.bank_sell_price == Decimal("42.200000")
    assert parsed.source_symbol == "GMS (gr)"
    assert parsed.source_name == "Gümüş"
    assert len(parsed.source_hash) == 64
    assert parsed.provider_reported_at is None
    assert parsed.indicative is True


def test_parser_fails_visibly_when_silver_row_is_missing() -> None:
    payload = b'{"Data":[{"Code":"USD","Symbol":"USD","BuyRate":"1","SellRate":"2"}]}'

    with pytest.raises(ProviderParseError, match="GMS"):
        parse_finance_portal_silver_quote(payload)


def test_parser_fails_visibly_when_required_price_field_changes() -> None:
    payload = (
        b'{"Data":[{"Code":"GMS","Symbol":"GMS (gr)",'
        b'"Name":"Gumus","Buy":"41,10","SellRate":"42,20"}]}'
    )

    with pytest.raises(ProviderParseError, match="BuyRate"):
        parse_finance_portal_silver_quote(payload)


def test_parser_rejects_zero_negative_and_inverted_prices() -> None:
    zero_payload = (
        b'{"Data":[{"Code":"GMS","Symbol":"GMS (gr)",'
        b'"Name":"Gumus","BuyRate":"0","SellRate":"42,20"}]}'
    )
    inverted_payload = (
        b'{"Data":[{"Code":"GMS","Symbol":"GMS (gr)",'
        b'"Name":"Gumus","BuyRate":"42,20","SellRate":"41,10"}]}'
    )

    with pytest.raises(DataQualityError, match="greater than zero"):
        parse_finance_portal_silver_quote(zero_payload)
    with pytest.raises(DataQualityError, match="sell price"):
        parse_finance_portal_silver_quote(inverted_payload)


def test_endpoint_resolver_discovers_endpoint_from_inline_addresses() -> None:
    def fake_http_get(url: str, timeout_seconds: float) -> bytes:
        assert url == KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL
        assert timeout_seconds == 10.0
        return (
            "<script>const addresses = {"
            f'"fn-rlrtd": "{DISCOVERED_PATH}",'
            ' "other": "/ck0d84?EB770F761E1233CCE1588AFFCAEBABFC"'
            "};</script>"
        ).encode()

    resolver = KuveytTurkEndpointResolver(http_get=fake_http_get)

    assert resolver.resolve_finance_portal_url() == DISCOVERED_URL


def test_endpoint_resolver_falls_back_to_core_js_finance_portal() -> None:
    seen_urls: list[str] = []

    def fake_http_get(url: str, _timeout_seconds: float) -> bytes:
        seen_urls.append(url)
        if url == KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL:
            return b"<script>const addresses = {};</script>"
        if url == KUVEYT_TURK_CORE_JS_URL:
            return f'ApiEndpoints={{financePortal:"{DISCOVERED_PATH}"}}'.encode()
        raise AssertionError(f"unexpected URL: {url}")

    resolver = KuveytTurkEndpointResolver(http_get=fake_http_get)

    assert resolver.resolve_finance_portal_url() == DISCOVERED_URL
    assert seen_urls == [KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL, KUVEYT_TURK_CORE_JS_URL]


def test_endpoint_resolver_fails_closed_when_endpoint_key_is_missing() -> None:
    def fake_http_get(url: str, _timeout_seconds: float) -> bytes:
        if url == KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL:
            return (
                b"<script>const addresses = {"
                b"'other':'/ck0d84?EB770F761E1233CCE1588AFFCAEBABFC'"
                b"};</script>"
            )
        if url == KUVEYT_TURK_CORE_JS_URL:
            return b"ApiEndpoints={accounts:'/ck0d84?EB770F761E1233CCE1588AFFCAEBABFC'}"
        raise AssertionError(f"unexpected URL: {url}")

    resolver = KuveytTurkEndpointResolver(http_get=fake_http_get)

    with pytest.raises(ProviderParseError, match="endpoint was not found"):
        resolver.resolve_finance_portal_url()


@pytest.mark.parametrize(
    "bad_path",
    [
        "/not-finance?B83A1EF44DD940F2FEC85646BDB25EA0",
        "/ck0d84?not-a-hash",
        "https://evil.example/ck0d84?B83A1EF44DD940F2FEC85646BDB25EA0",
        "https://www.kuveytturk.com.tr/login",
    ],
)
def test_endpoint_resolver_rejects_non_finance_or_absolute_paths(bad_path: str) -> None:
    def fake_http_get(_url: str, _timeout_seconds: float) -> bytes:
        return f"<script>const addresses = {{'fn-rlrtd':'{bad_path}'}};</script>".encode()

    resolver = KuveytTurkEndpointResolver(http_get=fake_http_get)

    with pytest.raises(ProviderParseError, match="not allowed"):
        resolver.resolve_finance_portal_url()


def test_provider_builds_price_quote_without_live_network() -> None:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    seen_urls: list[str] = []

    def fake_http_get(url: str, timeout_seconds: float) -> bytes:
        seen_urls.append(url)
        assert timeout_seconds == 10.0
        if url == KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL:
            return (
                f"<script>const addresses = {{'fn-rlrtd':'{DISCOVERED_PATH}'}};</script>"
            ).encode()
        if url == DISCOVERED_URL:
            return FIXTURE_PATH.read_bytes()
        raise AssertionError(f"unexpected URL: {url}")

    provider = KuveytTurkPriceProvider(
        clock=SimulatedClock(now),
        http_get=fake_http_get,
    )

    result = provider.fetch_quote_result(_silver_instrument())

    assert result.quote.bank_buy_price.amount == Decimal("41.100000")
    assert result.quote.bank_sell_price.amount == Decimal("42.200000")
    assert result.quote.observed_at == now
    assert result.quote.fetched_at == now
    assert result.quote.source == KUVEYT_TURK_SOURCE_NAME
    assert result.indicative is True
    assert len(result.source_hash) == 64
    assert seen_urls == [KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL, DISCOVERED_URL]


def test_provider_fails_closed_when_endpoint_discovery_breaks() -> None:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def fake_http_get(url: str, _timeout_seconds: float) -> bytes:
        if url in {KUVEYT_TURK_FINANCE_PORTAL_PAGE_URL, KUVEYT_TURK_CORE_JS_URL}:
            return b"<script>const addresses = {};</script>"
        message = f"provider should not fetch payload URL after discovery failure: {url}"
        raise AssertionError(message)

    provider = KuveytTurkPriceProvider(
        clock=SimulatedClock(now),
        http_get=fake_http_get,
    )

    with pytest.raises(ProviderParseError, match="endpoint was not found"):
        provider.fetch_quote_result(_silver_instrument())


def test_provider_keeps_explicit_url_override_for_configured_fallback() -> None:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    seen_urls: list[str] = []

    def fake_http_get(url: str, _timeout_seconds: float) -> bytes:
        seen_urls.append(url)
        return FIXTURE_PATH.read_bytes()

    provider = KuveytTurkPriceProvider(
        url=DISCOVERED_URL,
        clock=SimulatedClock(now),
        http_get=fake_http_get,
    )

    provider.fetch_quote_result(_silver_instrument())

    assert seen_urls == [DISCOVERED_URL]


def test_provider_rejects_unsupported_instrument() -> None:
    instrument = _silver_instrument().model_copy(update={"currency_code": "USD"})
    provider = KuveytTurkPriceProvider(http_get=lambda _url, _timeout: FIXTURE_PATH.read_bytes())

    with pytest.raises(DataQualityError, match="XAG/GRAM/TRY"):
        provider.fetch_quote(instrument)


def test_validate_freshness_rejects_stale_or_future_observations() -> None:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    validate_freshness(
        observed_at=now - timedelta(minutes=4),
        now=now,
        max_age=timedelta(minutes=5),
    )

    with pytest.raises(StaleDataError):
        validate_freshness(
            observed_at=now - timedelta(minutes=6),
            now=now,
            max_age=timedelta(minutes=5),
        )

    with pytest.raises(DataQualityError, match="future"):
        validate_freshness(
            observed_at=now + timedelta(seconds=1),
            now=now,
            max_age=timedelta(minutes=5),
        )
