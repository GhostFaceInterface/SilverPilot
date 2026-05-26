import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
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
from app.models import Asset, CollectorRun, PriceSnapshot, RawGlobalPrice, TechnicalIndicator

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
        backfill_script.backfill()

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
        db.close()

        # --- Test 2: Duplicate detection (Phase 2 & 3 set O(1) optimization) ---
        # Run again with the same mock data. It should identify all as duplicates
        backfill_script.backfill()

        db = TestingSessionLocal()
        runs = db.query(CollectorRun).all()
        assert len(runs) == 2
        assert runs[1].status == "success"
        assert runs[1].records_seen == 2
        assert runs[1].records_inserted == 0
        assert runs[1].duplicates == 2
        db.close()

        # --- Test 3: Failure scenario (Phase 1 Crash Safety) ---
        # Mock httpx to raise a connection error
        mock_get.side_effect = httpx.RequestError("Connection failed")

        with pytest.raises(httpx.RequestError):
            backfill_script.backfill()

        db = TestingSessionLocal()
        runs = db.query(CollectorRun).all()
        assert len(runs) == 3
        # Last run should have failed
        assert runs[2].status == "failed"
        assert "Connection failed" in runs[2].error_message
        db.close()
