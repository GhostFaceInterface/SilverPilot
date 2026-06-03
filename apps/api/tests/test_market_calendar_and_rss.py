"""
Tests for modular COMEX market calendar functions and Generic RSS news collectors.

Tests cover:
- is_comex_weekend: Boundary cases around Fri 17:00 ET → Sun 18:00 ET
- is_comex_maintenance: Weekday daily maintenance windows (Mon-Thu 17:00-18:00 ET)
- is_comex_market_closed: Combined composition of weekend + maintenance
- parse_generic_rss: RSS 2.0 and Atom XML parsing
- collect_rss_news: Failover URL behavior with mock HTTP
- RSS_FEEDS: Data structure integrity
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from xml.etree import ElementTree

from app.core.config import get_settings
from app.collectors.public_sources import (
    RSS_FEEDS,
    GENERIC_RSS_PARSER_VERSION,
    parse_generic_rss,
    collect_rss_news,
    CollectorError,
)


# ==============================================================================
# Faz 1: Modular Market Calendar Tests
# ==============================================================================


class TestIsComexWeekend:
    """Tests for is_comex_weekend: Friday 17:00 ET → Sunday 18:00 ET."""

    def setup_method(self):
        self.settings = get_settings()
        self._original_env = self.settings.app_env
        self.settings.app_env = "production"

    def teardown_method(self):
        self.settings.app_env = self._original_env

    def test_friday_before_close_is_open(self):
        """Friday 16:59 ET → market OPEN (weekend = False)."""
        from app.risk.service import is_comex_weekend

        # Friday 16:59 EDT (UTC-4) = Friday 20:59 UTC
        dt = datetime(2026, 5, 29, 20, 59, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is False

    def test_friday_at_close_is_weekend(self):
        """Friday 17:00 ET → market CLOSED (weekend = True)."""
        from app.risk.service import is_comex_weekend

        # Friday 17:00 EDT (UTC-4) = Friday 21:00 UTC
        dt = datetime(2026, 5, 29, 21, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is True

    def test_saturday_all_day_is_weekend(self):
        """Saturday 12:00 ET → market CLOSED (weekend = True)."""
        from app.risk.service import is_comex_weekend

        dt = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is True

    def test_sunday_before_open_is_weekend(self):
        """Sunday 12:00 ET → market CLOSED (weekend = True)."""
        from app.risk.service import is_comex_weekend

        dt = datetime(2026, 5, 31, 16, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is True

    def test_sunday_at_open_is_open(self):
        """Sunday 18:00 ET → market OPEN (weekend = False)."""
        from app.risk.service import is_comex_weekend

        # Sunday 18:00 EDT (UTC-4) = Sunday 22:00 UTC
        dt = datetime(2026, 5, 31, 22, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is False

    def test_sunday_after_open_is_open(self):
        """Sunday 19:00 ET → market OPEN (weekend = False)."""
        from app.risk.service import is_comex_weekend

        dt = datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is False

    def test_wednesday_midday_is_not_weekend(self):
        """Wednesday 12:00 ET → not a weekend."""
        from app.risk.service import is_comex_weekend

        dt = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is False

    def test_test_env_always_returns_false(self):
        """In test env, is_comex_weekend always returns False."""
        from app.risk.service import is_comex_weekend

        self.settings.app_env = "test"
        # Even Saturday should return False in test env
        dt = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)
        assert is_comex_weekend(dt) is False


class TestIsComexMaintenance:
    """Tests for is_comex_maintenance: Mon-Thu 17:00-17:59 ET."""

    def setup_method(self):
        self.settings = get_settings()
        self._original_env = self.settings.app_env
        self.settings.app_env = "production"

    def teardown_method(self):
        self.settings.app_env = self._original_env

    def test_tuesday_maintenance_window(self):
        """Tuesday 17:30 ET → maintenance = True."""
        from app.risk.service import is_comex_maintenance

        # Tuesday 17:30 EDT (UTC-4) = Tuesday 21:30 UTC
        dt = datetime(2026, 5, 26, 21, 30, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is True

    def test_tuesday_before_maintenance(self):
        """Tuesday 16:59 ET → maintenance = False."""
        from app.risk.service import is_comex_maintenance

        # Tuesday 16:59 EDT (UTC-4) = Tuesday 20:59 UTC
        dt = datetime(2026, 5, 26, 20, 59, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is False

    def test_tuesday_after_maintenance(self):
        """Tuesday 18:00 ET → maintenance = False."""
        from app.risk.service import is_comex_maintenance

        # Tuesday 18:00 EDT (UTC-4) = Tuesday 22:00 UTC
        dt = datetime(2026, 5, 26, 22, 0, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is False

    def test_friday_no_maintenance(self):
        """Friday 17:00 ET → NOT maintenance (it's weekend close, handled by is_comex_weekend)."""
        from app.risk.service import is_comex_maintenance

        dt = datetime(2026, 5, 29, 21, 0, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is False

    def test_saturday_no_maintenance(self):
        """Saturday → NOT maintenance."""
        from app.risk.service import is_comex_maintenance

        dt = datetime(2026, 5, 30, 21, 0, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is False

    def test_monday_maintenance(self):
        """Monday 17:00 ET → maintenance = True."""
        from app.risk.service import is_comex_maintenance

        # Monday 17:00 EDT (UTC-4) = Monday 21:00 UTC
        dt = datetime(2026, 5, 25, 21, 0, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is True

    def test_thursday_maintenance(self):
        """Thursday 17:45 ET → maintenance = True."""
        from app.risk.service import is_comex_maintenance

        # Thursday 17:45 EDT (UTC-4) = Thursday 21:45 UTC
        dt = datetime(2026, 5, 28, 21, 45, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is True

    def test_test_env_always_returns_false(self):
        """In test env, is_comex_maintenance always returns False."""
        from app.risk.service import is_comex_maintenance

        self.settings.app_env = "test"
        dt = datetime(2026, 5, 26, 21, 30, tzinfo=timezone.utc)
        assert is_comex_maintenance(dt) is False


class TestIsComexMarketClosed:
    """Tests for is_comex_market_closed: composition of weekend OR maintenance."""

    def setup_method(self):
        self.settings = get_settings()
        self._original_env = self.settings.app_env
        self.settings.app_env = "production"

    def teardown_method(self):
        self.settings.app_env = self._original_env

    def test_closed_on_saturday(self):
        from app.risk.service import is_comex_market_closed

        dt = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(dt) is True

    def test_closed_on_maintenance(self):
        from app.risk.service import is_comex_market_closed

        dt = datetime(2026, 5, 26, 21, 30, tzinfo=timezone.utc)
        assert is_comex_market_closed(dt) is True

    def test_open_on_wednesday_noon(self):
        from app.risk.service import is_comex_market_closed

        dt = datetime(2026, 5, 27, 16, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(dt) is False

    def test_open_after_sunday_reopen(self):
        from app.risk.service import is_comex_market_closed

        dt = datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc)
        assert is_comex_market_closed(dt) is False


# ==============================================================================
# Faz 2: Generic RSS Parser Tests
# ==============================================================================


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
  <title>Silver hits $30</title>
  <link>https://example.com/silver-30</link>
  <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
  <guid>https://example.com/silver-30</guid>
  <description>Silver prices surge to $30 per ounce.</description>
  <category>Metals</category>
  <category>Silver</category>
</item>
<item>
  <title>Gold stabilizes at $2,400</title>
  <link>https://example.com/gold-2400</link>
  <pubDate>Mon, 01 Jun 2026 09:00:00 +0000</pubDate>
</item>
<item>
  <title></title>
  <link>https://example.com/empty-title</link>
</item>
</channel>
</rss>"""


SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry>
  <title>Fed rate decision pending</title>
  <link href="https://example.com/fed-rate"/>
  <updated>2026-06-01T08:00:00Z</updated>
</entry>
<entry>
  <title>Turkey CPI rises</title>
  <link href="https://example.com/turkey-cpi"/>
  <updated>2026-06-01T07:00:00Z</updated>
</entry>
</feed>"""


INVALID_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<root><data>Not an RSS feed</data></root>"""


class TestParseGenericRss:
    """Tests for parse_generic_rss: RSS 2.0 and Atom parsing."""

    def test_rss_2_0_parsing(self):
        """Standard RSS 2.0 with multiple items, categories, and optional fields."""
        items = parse_generic_rss(SAMPLE_RSS_XML)
        # Empty title item should be skipped
        assert len(items) == 2

        silver_item = items[0]
        assert silver_item.title == "Silver hits $30"
        assert silver_item.url == "https://example.com/silver-30"
        assert silver_item.published_at is not None
        assert silver_item.payload["guid"] == "https://example.com/silver-30"
        assert silver_item.payload["categories"] == ["Metals", "Silver"]
        assert silver_item.payload["source_type"] == "rss_feed"

    def test_rss_2_0_skips_empty_title(self):
        """Items with empty titles should be filtered out."""
        items = parse_generic_rss(SAMPLE_RSS_XML)
        titles = [item.title for item in items]
        assert "" not in titles

    def test_atom_format_parsing(self):
        """Atom feed parsing with <entry> and <link href=...>."""
        items = parse_generic_rss(SAMPLE_ATOM_XML)
        assert len(items) == 2

        fed_item = items[0]
        assert fed_item.title == "Fed rate decision pending"
        assert fed_item.url == "https://example.com/fed-rate"
        assert fed_item.published_at is not None
        assert fed_item.payload["source_type"] == "atom_feed"

    def test_invalid_xml_raises_error(self):
        """Non-RSS XML should raise CollectorError."""
        with pytest.raises(CollectorError, match="no <channel> or <entry> elements"):
            parse_generic_rss(INVALID_RSS_XML)

    def test_empty_channel_raises_error(self):
        """RSS with empty channel (no items) returns empty list."""
        xml = """<?xml version="1.0"?><rss><channel></channel></rss>"""
        items = parse_generic_rss(xml)
        assert items == []

    def test_malformed_xml_raises_parse_error(self):
        """Completely malformed XML should raise an error."""
        with pytest.raises(ElementTree.ParseError):
            parse_generic_rss("not even xml <<<<")


# ==============================================================================
# Faz 2: RSS Collector with Failover Tests
# ==============================================================================


class TestCollectRssNews:
    """Tests for collect_rss_news with failover URL behavior."""

    def test_first_url_succeeds(self, db_session):
        """First URL succeeds → collector returns success immediately."""
        with patch("app.collectors.public_sources._fetch_text", return_value=SAMPLE_RSS_XML):
            run, inserted = collect_rss_news(
                db_session,
                source="kitco-rss",
                urls=["https://primary.example.com/rss", "https://backup.example.com/rss"],
            )
        assert run.status == "success"
        assert inserted == 2  # Two valid items in SAMPLE_RSS_XML

    def test_first_url_fails_second_succeeds(self, db_session):
        """First URL raises exception → falls back to second URL successfully."""
        call_count = 0

        def mock_fetch(url, *, settings, client):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection refused")
            return SAMPLE_RSS_XML

        with patch("app.collectors.public_sources._fetch_text", side_effect=mock_fetch):
            run, inserted = collect_rss_news(
                db_session,
                source="kitco-rss",
                urls=["https://dead.example.com/rss", "https://alive.example.com/rss"],
            )
        assert call_count == 2
        assert run.status == "success"
        assert inserted == 2

    def test_all_urls_fail(self, db_session):
        """All URLs fail → collector records failure and returns 0 inserted."""
        with patch(
            "app.collectors.public_sources._fetch_text",
            side_effect=Exception("Network unreachable"),
        ):
            run, inserted = collect_rss_news(
                db_session,
                source="kitco-rss",
                urls=["https://dead1.example.com", "https://dead2.example.com"],
            )
        assert run.status == "failed"
        assert inserted == 0

    def test_empty_feed_tries_next_url(self, db_session):
        """Feed returns valid XML but zero items → tries next URL."""
        empty_rss = """<?xml version="1.0"?><rss><channel></channel></rss>"""
        call_count = 0

        def mock_fetch(url, *, settings, client):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return empty_rss
            return SAMPLE_RSS_XML

        with patch("app.collectors.public_sources._fetch_text", side_effect=mock_fetch):
            run, inserted = collect_rss_news(
                db_session,
                source="fxstreet-rss",
                urls=["https://empty.example.com", "https://full.example.com"],
            )
        assert call_count == 2
        assert inserted == 2

    def test_deduplication_on_second_call(self, db_session):
        """Second collection of same items should not duplicate records."""
        with patch("app.collectors.public_sources._fetch_text", return_value=SAMPLE_RSS_XML):
            _run1, inserted1 = collect_rss_news(
                db_session,
                source="kitco-rss",
                urls=["https://example.com/rss"],
            )
            _run2, inserted2 = collect_rss_news(
                db_session,
                source="kitco-rss",
                urls=["https://example.com/rss"],
            )
        assert inserted1 == 2
        assert inserted2 == 0  # Duplicates should be filtered


# ==============================================================================
# Faz 2: RSS_FEEDS Data Integrity Tests
# ==============================================================================


class TestRssFeedsConfig:
    """Structural integrity checks for the RSS_FEEDS configuration."""

    def test_all_sources_have_at_least_two_urls(self):
        """Every RSS source must have at least 2 failover URLs."""
        for source, urls in RSS_FEEDS.items():
            assert len(urls) >= 2, f"{source} has only {len(urls)} URL(s), needs >= 2 for failover"

    def test_all_urls_are_https(self):
        """All feed URLs must use HTTPS."""
        for source, urls in RSS_FEEDS.items():
            for url in urls:
                assert url.startswith("https://"), f"{source} URL is not HTTPS: {url}"

    def test_expected_sources_exist(self):
        """All 4 planned RSS sources should be registered."""
        expected = {"kitco-rss", "bloomberght-rss", "fxstreet-rss", "investing-rss"}
        assert expected.issubset(set(RSS_FEEDS.keys()))

    def test_parser_version_is_set(self):
        """GENERIC_RSS_PARSER_VERSION must be a non-empty string."""
        assert isinstance(GENERIC_RSS_PARSER_VERSION, str)
        assert len(GENERIC_RSS_PARSER_VERSION) > 0


class TestParseRssDatetime:
    """Tests for _parse_rss_datetime covering RFC 2822, ISO 8601, and custom formats."""

    def test_rfc2822_formats(self):
        from app.collectors.public_sources import _parse_rss_datetime

        # Standard GMT RFC 2822
        dt = _parse_rss_datetime("Mon, 01 Jun 2026 10:00:00 +0000")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # RFC 2822 with named TZ
        dt = _parse_rss_datetime("Mon, 01 Jun 2026 10:00:00 GMT")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # RFC 2822 with negative offset (-0400 -> UTC-4 -> should become 14:00:00 UTC)
        dt = _parse_rss_datetime("Mon, 01 Jun 2026 10:00:00 -0400")
        assert dt == datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone.utc)

    def test_iso8601_formats(self):
        from app.collectors.public_sources import _parse_rss_datetime

        # Standard with Z
        dt = _parse_rss_datetime("2026-06-01T10:00:00Z")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # With positive offset
        dt = _parse_rss_datetime("2026-06-01T12:00:00+02:00")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # With fractional seconds and Z
        dt = _parse_rss_datetime("2026-06-01T10:00:00.123Z")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, 123000, tzinfo=timezone.utc)

    def test_custom_formats(self):
        from app.collectors.public_sources import _parse_rss_datetime

        # YYYY-MM-DD HH:MM:SS
        dt = _parse_rss_datetime("2026-06-01 10:00:00")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # DD.MM.YYYY HH:MM:SS
        dt = _parse_rss_datetime("01.06.2026 10:00:00")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

        # YYYY-MM-DDTHH:MM:SS.fZ
        dt = _parse_rss_datetime("2026-06-01T10:00:00.123456Z")
        assert dt == datetime(2026, 6, 1, 10, 0, 0, 123456, tzinfo=timezone.utc)

    def test_empty_or_none(self):
        from app.collectors.public_sources import _parse_rss_datetime

        assert _parse_rss_datetime(None) is None
        assert _parse_rss_datetime("") is None
        assert _parse_rss_datetime("   ") is None

    def test_invalid_format_raises_collector_error(self):
        from app.collectors.public_sources import _parse_rss_datetime

        with pytest.raises(CollectorError, match="Unsupported RSS datetime format"):
            _parse_rss_datetime("not-a-date")
