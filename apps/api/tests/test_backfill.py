import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import httpx

# Add root folder to sys.path to resolve 'scripts' module
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from app.core.db import Base
from app.models import Asset, CollectorRun, PriceSnapshot, RawGlobalPrice, TechnicalIndicator, MarketBar
from app.services.indicator_readiness import get_indicator_readiness

# Import the backfill script
import scripts.backfill_history as backfill_script


def test_backfill_success_and_failure():
    # 1. Setup in-memory SQLite database
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Pre-seed the XAG asset
    db = TestingSessionLocal()
    xag = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
    db.add(xag)
    db.commit()
    db.close()

    # Mock response for Yahoo Finance API
    mock_yahoo_response = {
        "chart": {
            "result": [
                {
                    "timestamp": [1716240000, 1716326400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [28.5, 29.0],
                                "high": [29.2, 29.5],
                                "low": [28.3, 28.8],
                                "close": [28.8, 29.3],
                                "volume": [1000, 1500],
                            }
                        ]
                    },
                }
            ]
        }
    }

    # Patch SessionLocal and httpx.get
    with patch("scripts.backfill_history.SessionLocal", TestingSessionLocal), patch("httpx.get") as mock_get:
        # Setup mock HTTP response for success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_yahoo_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # --- Test 1: Successful backfill ---
        backfill_script.backfill(min_bars=2)

        # Verify database inserts
        db = TestingSessionLocal()
        runs = db.query(CollectorRun).all()
        assert len(runs) == 1
        assert runs[0].status == "success"
        assert runs[0].records_seen == 2
        assert runs[0].records_inserted == 4
        assert runs[0].duplicates == 0

        snapshots = db.query(PriceSnapshot).all()
        assert len(snapshots) == 4
        assert snapshots[0].buy_price == Decimal("28.8")
        assert snapshots[2].buy_price == Decimal("29.3")

        raw_prices = db.query(RawGlobalPrice).all()
        assert len(raw_prices) == 4

        indicators = db.query(TechnicalIndicator).all()
        # Since we ran calculate_indicators, verify it populated indicators
        assert len(indicators) == 4
        assert db.query(MarketBar).count() == 4
        assert all(indicator.market_bar_id is not None for indicator in indicators)
        assert all(indicator.calculation_version == "technical-indicators-v2" for indicator in indicators)
        assert indicators[-1].input_bar_count == 2
        db.close()

        # --- Test 2: Duplicate detection (Phase 2 & 3 set O(1) optimization) ---
        # Run again with the same mock data. It should identify all as duplicates
        backfill_script.backfill(min_bars=2)

        db = TestingSessionLocal()
        runs = db.query(CollectorRun).all()
        assert len(runs) == 2
        assert runs[1].status == "success"
        assert runs[1].records_seen == 2
        assert runs[1].records_inserted == 0
        assert runs[1].duplicates == 2
        db.close()

        # --- Test 3: Failure scenario before DB mutation
        mock_get.side_effect = httpx.RequestError("Connection failed")

        with pytest.raises(httpx.RequestError):
            backfill_script.backfill(min_bars=2)

        db = TestingSessionLocal()
        runs = db.query(CollectorRun).all()
        assert len(runs) == 2
        db.close()


def test_1d_backfill_creates_marketbar_linked_ready_indicators():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    start = datetime.now(UTC) - timedelta(days=59)
    rows = []
    for idx in range(60):
        price = 28 + (idx / 10)
        rows.append(
            {
                "timestamp": int((start + timedelta(days=idx)).timestamp()),
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 1000 + idx,
            }
        )
    history = pd.DataFrame(rows)

    with (
        patch("scripts.backfill_history.SessionLocal", TestingSessionLocal),
        patch("scripts.backfill_history.fetch_yahoo_daily_history", return_value=history),
    ):
        backfill_script.backfill(assets=["XAG_GRAM"], timeframes=["1d"], min_bars=60)

    db = TestingSessionLocal()
    try:
        readiness = get_indicator_readiness(
            db,
            asset_symbol="XAG_GRAM",
            timeframe="1d",
            required_min_bar_count=50,
            max_age_minutes=48 * 60,
            allowed_sources=("yahoo-si-f",),
        )
        assert readiness.status == "ready"
        assert readiness.usable is True
        assert readiness.input_bar_count == 60
        assert readiness.market_bar_id is not None
        assert db.query(MarketBar).count() == 60
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
