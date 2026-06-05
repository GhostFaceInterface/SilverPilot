"""Tests for the Technical Indicator Engine (Phase 3.6).

Unit tests for app.services.indicators.calculate_indicators.
Integration tests for live indicator wiring in app.collectors.service.ingest_global_price.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from sqlalchemy import select

from app.models import Asset, MarketBar, PriceSnapshot, TechnicalIndicator
from app.services.indicators import calculate_indicators


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_df(n: int, base_price: float = 30.0, volatility: float = 0.5) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with n rows."""
    import random

    random.seed(42)
    records = []
    price = base_price
    for _ in range(n):
        change = random.uniform(-volatility, volatility)
        price = max(1.0, price + change)
        high = price + abs(random.uniform(0.1, 0.3))
        low = price - abs(random.uniform(0.1, 0.3))
        records.append({"high": high, "low": low, "close": price})
    return pd.DataFrame(records)


# ===========================================================================
# Unit Tests — calculate_indicators
# ===========================================================================


class TestCalculateIndicatorsBasic:
    """Test with a large enough DataFrame (200+ rows) to produce all indicators."""

    def test_all_indicator_columns_present(self):
        df = _make_ohlcv_df(250)
        result = calculate_indicators(df)
        expected_cols = [
            "rsi_14",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "bb_upper_20_2",
            "bb_middle_20_2",
            "bb_lower_20_2",
            "sma_20",
            "sma_50",
            "sma_200",
            "ema_20",
            "ema_50",
            "ema_200",
            "adx_14",
            "plus_di_14",
            "minus_di_14",
            "bb_bandwidth_20_2",
            "bb_percent_b_20_2",
            "atr_percent_14",
            "rsi_slope_1",
            "macd_histogram_slope_1",
            "atr_14",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_last_row_has_values(self):
        df = _make_ohlcv_df(250)
        result = calculate_indicators(df)
        last = result.iloc[-1]
        for col in ["rsi_14", "macd_line", "sma_20", "sma_50", "sma_200", "atr_14"]:
            assert not pd.isna(last[col]), f"{col} should not be NaN at row 250"


class TestCalculateIndicatorsEmpty:
    """Test that an empty DataFrame does not raise and fills with None."""

    def test_empty_dataframe_no_error(self):
        df = pd.DataFrame(columns=["high", "low", "close"])
        result = calculate_indicators(df)
        assert len(result) == 0

    def test_single_row_no_error(self):
        df = pd.DataFrame([{"high": 30.5, "low": 29.5, "close": 30.0}])
        result = calculate_indicators(df)
        assert len(result) == 1
        # All indicators should be None/NaN for single row
        for col in ["rsi_14", "sma_20", "sma_200", "atr_14"]:
            assert col in result.columns


class TestCalculateIndicatorsInsufficientData:
    """Test NaN handling with fewer bars than needed."""

    def test_rsi_nan_first_rows_then_value(self):
        df = _make_ohlcv_df(20)
        result = calculate_indicators(df)
        # RSI uses ewm(alpha=1/14, min_periods=14) on diff() output.
        # diff() makes row 0 NaN, so first 14 RSI values are NaN.
        # Row index 14 (15th row) should have the first valid RSI value.
        for i in range(14):
            assert pd.isna(result.iloc[i]["rsi_14"]), f"RSI at row {i} should be NaN"
        assert not pd.isna(result.iloc[14]["rsi_14"]), "RSI at row 15 should have a value"

    def test_sma_200_requires_200_bars(self):
        df = _make_ohlcv_df(201)
        result = calculate_indicators(df)
        # SMA200 at row 198 (index) should be NaN
        assert pd.isna(result.iloc[198]["sma_200"]), "SMA200 at row 199 should be NaN"
        # SMA200 at row 199 (index) should have a value (200th bar)
        assert not pd.isna(result.iloc[199]["sma_200"]), "SMA200 at row 200 should have a value"


class TestRSIBoundaries:
    """Test that RSI values are always within [0, 100]."""

    def test_rsi_within_bounds(self):
        df = _make_ohlcv_df(300)
        result = calculate_indicators(df)
        rsi_values = result["rsi_14"].dropna()
        assert len(rsi_values) > 0
        assert rsi_values.min() >= 0, f"RSI below 0: {rsi_values.min()}"
        assert rsi_values.max() <= 100, f"RSI above 100: {rsi_values.max()}"


class TestBollingerBandOrdering:
    """Test that bb_lower < bb_middle < bb_upper always holds."""

    def test_band_ordering(self):
        df = _make_ohlcv_df(100)
        result = calculate_indicators(df)
        valid = result.dropna(subset=["bb_lower_20_2", "bb_middle_20_2", "bb_upper_20_2"])
        assert len(valid) > 0
        for _, row in valid.iterrows():
            assert row["bb_lower_20_2"] <= row["bb_middle_20_2"], "BB lower > middle"
            assert row["bb_middle_20_2"] <= row["bb_upper_20_2"], "BB middle > upper"


# ===========================================================================
# Integration Tests — Live Wiring (ingest_global_price → TechnicalIndicator)
# ===========================================================================


class TestIngestGlobalPriceIndicatorWiring:
    """Test that ingest_global_price creates TechnicalIndicator records."""

    def test_creates_indicator_for_yahoo_source(self, db_session):
        """When source is yahoo-si-f, a TechnicalIndicator row should be created."""
        from app.collectors.service import ingest_global_price

        # Setup: create XAG asset
        asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
        db_session.add(asset)
        db_session.commit()

        # Seed some historical snapshots so indicators can compute
        base_time = datetime(2025, 1, 1, tzinfo=UTC)
        for i in range(50):
            snap = PriceSnapshot(
                asset_id=asset.id,
                source="yahoo-si-f",
                buy_price=Decimal("30.500000"),
                sell_price=Decimal("30.400000"),
                mid_price=Decimal("30.450000"),
                currency="USD",
                spread_absolute=Decimal("0.100000"),
                spread_percent=Decimal("0.328410"),
                observed_at=base_time + timedelta(minutes=5 * i),
            )
            db_session.add(snap)
        db_session.commit()

        # Act: ingest a new global price
        observed_at = base_time + timedelta(minutes=5 * 50)
        run, inserted, snapshot = ingest_global_price(
            db_session,
            source="yahoo-si-f",
            asset_symbol="XAG",
            buy_price=Decimal("30.600000"),
            sell_price=Decimal("30.500000"),
            currency="USD",
            observed_at=observed_at,
            fetched_at=datetime.now(UTC),
            payload={"test": True},
            raw_payload="test_raw_payload",
            parser_version="test-v1",
            collector_name="test_global_xag_usd",
        )

        # Assert: snapshot was created
        assert inserted is True
        assert snapshot is not None

        # Assert: TechnicalIndicator was also created
        indicator = db_session.execute(
            select(TechnicalIndicator).where(TechnicalIndicator.price_snapshot_id == snapshot.id)
        ).scalar_one_or_none()
        assert indicator is not None, "TechnicalIndicator should be created for yahoo-si-f source"
        assert indicator.timeframe == "5m"
        assert indicator.close_usd_oz == snapshot.mid_price
        assert indicator.market_bar_id is not None
        assert indicator.calculation_version == "technical-indicators-v2"
        assert indicator.input_bar_count == 51
        assert indicator.quality_status == "ok"
        assert indicator.ema_20 is not None
        assert indicator.adx_14 is not None
        assert indicator.bb_bandwidth_20_2 is not None

        market_bar = db_session.get(MarketBar, indicator.market_bar_id)
        assert market_bar is not None
        assert market_bar.asset_id == asset.id
        assert market_bar.source == "yahoo-si-f"
        assert market_bar.timeframe == "5m"
        assert market_bar.close == snapshot.mid_price
        assert market_bar.last_price_snapshot_id == snapshot.id
        assert market_bar.bar_builder_version == "market-bars-v1"

    def test_indicator_failure_does_not_block_snapshot(self, db_session):
        """If indicator calculation fails, the price snapshot must still be saved."""
        from app.collectors.service import ingest_global_price

        # Setup: create XAG asset
        asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
        db_session.add(asset)
        db_session.commit()

        # Act: Mock calculate_indicators to raise an exception
        observed_at = datetime(2025, 6, 1, tzinfo=UTC)
        with patch("app.collectors.service.calculate_indicators", side_effect=RuntimeError("test boom")):
            run, inserted, snapshot = ingest_global_price(
                db_session,
                source="yahoo-si-f",
                asset_symbol="XAG",
                buy_price=Decimal("31.000000"),
                sell_price=Decimal("30.900000"),
                currency="USD",
                observed_at=observed_at,
                fetched_at=datetime.now(UTC),
                payload={"test_isolation": True},
                raw_payload="test_isolation_payload",
                parser_version="test-v1",
                collector_name="test_global_xag_usd",
            )

        # Assert: snapshot was still saved despite indicator failure
        assert inserted is True
        assert snapshot is not None
        assert snapshot.id is not None
        assert snapshot.collector_run_id == run.id

        # Assert: no indicator was created (it failed)
        indicator = db_session.execute(
            select(TechnicalIndicator).where(TechnicalIndicator.price_snapshot_id == snapshot.id)
        ).scalar_one_or_none()
        assert indicator is None, "No TechnicalIndicator should exist when calculation fails"

    def test_market_bars_keep_xag_and_xag_gram_separate(self, db_session):
        """Replicated gram snapshots must not share market bars with XAG ounce snapshots."""
        from app.collectors.service import ingest_global_price

        xag = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
        xag_gram = Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True)
        db_session.add_all([xag, xag_gram])
        db_session.commit()

        base_time = datetime(2025, 1, 1, tzinfo=UTC)
        for i in range(20):
            ingest_global_price(
                db_session,
                source="yahoo-si-f",
                asset_symbol="XAG",
                buy_price=Decimal("31.100000") + Decimal(i) / Decimal("100"),
                sell_price=Decimal("31.000000") + Decimal(i) / Decimal("100"),
                currency="USD",
                observed_at=base_time + timedelta(minutes=5 * i),
                fetched_at=base_time + timedelta(minutes=5 * i),
                payload={"i": i},
                raw_payload=f"payload-{i}",
                parser_version="test-v1",
                collector_name="test_global_xag_usd",
            )

        xag_bars = db_session.execute(select(MarketBar).where(MarketBar.asset_id == xag.id)).scalars().all()
        gram_bars = db_session.execute(select(MarketBar).where(MarketBar.asset_id == xag_gram.id)).scalars().all()

        assert xag_bars
        assert gram_bars
        assert {bar.asset_id for bar in xag_bars} == {xag.id}
        assert {bar.asset_id for bar in gram_bars} == {xag_gram.id}
        assert xag_bars[-1].close != gram_bars[-1].close

    def test_indicator_updates_existing_row_for_same_market_bar(self, db_session):
        from app.collectors.service import ingest_global_price

        asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
        db_session.add(asset)
        db_session.commit()

        base_time = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        for i in range(15):
            ingest_global_price(
                db_session,
                source="yahoo-si-f",
                asset_symbol="XAG",
                buy_price=Decimal("30.100000") + Decimal(i) / Decimal("100"),
                sell_price=Decimal("30.000000") + Decimal(i) / Decimal("100"),
                currency="USD",
                observed_at=base_time + timedelta(minutes=5 * i),
                fetched_at=base_time + timedelta(minutes=5 * i),
                payload={"i": i},
                raw_payload=f"payload-{i}",
                parser_version="test-v1",
                collector_name="test_global_xag_usd",
            )

        same_bar_time = base_time + timedelta(minutes=70, seconds=30)
        _, _, latest_snapshot = ingest_global_price(
            db_session,
            source="yahoo-si-f",
            asset_symbol="XAG",
            buy_price=Decimal("31.000000"),
            sell_price=Decimal("30.900000"),
            currency="USD",
            observed_at=same_bar_time,
            fetched_at=same_bar_time,
            payload={"same_bar": True},
            raw_payload="same-bar-payload",
            parser_version="test-v1",
            collector_name="test_global_xag_usd",
        )

        latest_bar = db_session.execute(
            select(MarketBar).where(MarketBar.last_price_snapshot_id == latest_snapshot.id)
        ).scalar_one()
        indicators = (
            db_session.execute(select(TechnicalIndicator).where(TechnicalIndicator.market_bar_id == latest_bar.id))
            .scalars()
            .all()
        )

        assert len(indicators) == 1
        assert indicators[0].price_snapshot_id == latest_snapshot.id
        assert latest_bar.sample_count == 2

    def test_no_indicator_for_bank_source(self, db_session):
        """Bank sources (kuveyt-public-silver-page) should NOT trigger indicator calculation."""
        from app.collectors.service import ingest_global_price

        asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
        db_session.add(asset)
        db_session.commit()

        observed_at = datetime(2025, 7, 1, tzinfo=UTC)
        run, inserted, snapshot = ingest_global_price(
            db_session,
            source="kuveyt-public-silver-page",
            asset_symbol="XAG",
            buy_price=Decimal("32.000000"),
            sell_price=Decimal("31.500000"),
            currency="USD",
            observed_at=observed_at,
            fetched_at=datetime.now(UTC),
            payload={"test_bank": True},
            raw_payload="test_bank_payload",
            parser_version="test-v1",
            collector_name="test_kuveyt",
        )

        assert inserted is True
        indicator_count = (
            db_session.execute(select(TechnicalIndicator).where(TechnicalIndicator.bar_timestamp == observed_at))
            .scalars()
            .all()
        )
        assert len(indicator_count) == 0, "No indicator should be created for bank sources"
