import os
import sys
import json
import shutil
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Sys path setup to import scripts from project root
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from app.core.db import Base, get_db
from app.main import create_app
from app.models import Asset, PriceSnapshot, RawFxRate, TechnicalIndicator, HistoricalAgentCache, AgentMemoryEvent
from app.core.config import get_settings, Settings
from scripts.build_dataset import build_dataset


def make_test_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Pre-seed basic Asset and required records
    db = TestingSession()
    try:
        asset = Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True)
        db.add(asset)
        db.commit()
    finally:
        db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    def override_get_settings():
        return Settings(agent_api_token="test_token")

    app.dependency_overrides[get_settings] = override_get_settings

    return TestClient(app), TestingSession


def seed_mock_history(TestingSession, start_time: datetime, count: int = 400):
    from app.models import CollectorRun

    db = TestingSession()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one()

        # Create a mock collector run to satisfy RawFxRate integrity constraints
        run = CollectorRun(
            collector_name="tcmb_usd_try",
            source="tcmb-today-xml",
            status="success",
            records_seen=1,
            records_inserted=1,
            started_at=start_time,
            finished_at=start_time,
            details_json={},
        )
        db.add(run)
        db.flush()

        for i in range(count):
            t = start_time + timedelta(minutes=i * 15)

            # Linearly increasing price by default
            mid = 20.0 + i * 0.1

            # Introduce a sharp price drop at step 200 to test max_drawdown_3d
            if i == 200:
                mid = 30.0  # drop from 40.0 to 30.0

            buy_price = mid * 1.005
            sell_price = mid * 0.995

            # Use explicit spread_percent for first half, and 0 for second half to test fallback logic
            spread = 1.0 if i < (count // 2) else 0.0

            db.add(
                PriceSnapshot(
                    asset_id=asset.id,
                    source="kuveyt_public_silver",
                    buy_price=Decimal(str(buy_price)),
                    sell_price=Decimal(str(sell_price)),
                    mid_price=Decimal(str(mid)),
                    currency="TRY",
                    spread_absolute=Decimal(str(buy_price - sell_price)),
                    spread_percent=Decimal(str(spread)),
                    observed_at=t,
                    is_degraded=False,
                )
            )

            # Seed RawFxRates every hour (4 intervals)
            if i % 4 == 0:
                db.add(
                    RawFxRate(
                        collector_run_id=run.id,
                        source="tcmb",
                        base_currency="USD",
                        quote_currency="TRY",
                        rate=Decimal(str(32.0 + i * 0.01)),
                        observed_at=t,
                        fetched_at=t,
                        raw_payload_hash=f"fx-hash-{i}",
                        parser_version="1",
                        payload_json={},
                    )
                )

            # Seed TechnicalIndicator every hour (4 intervals)
            if i % 4 == 0:
                db.add(
                    TechnicalIndicator(
                        bar_timestamp=t,
                        timeframe="15m",
                        rsi_14=Decimal("50.0"),
                        macd_line=Decimal("0.0"),
                        macd_signal=Decimal("0.0"),
                        macd_histogram=Decimal("0.0"),
                        bb_upper_20_2=Decimal("0.0"),
                        bb_middle_20_2=Decimal("0.0"),
                        bb_lower_20_2=Decimal("0.0"),
                        sma_20=Decimal("0.0"),
                        sma_50=Decimal("0.0"),
                        sma_200=Decimal("0.0"),
                        atr_14=Decimal("0.5"),
                        xau_xag_ratio=Decimal(str(80.0 + i * 0.05)),
                    )
                )

        # Seed Sentiment cache and events
        # A. Seeding Cache at index 100
        t_cache = start_time + timedelta(minutes=100 * 15)
        db.add(
            HistoricalAgentCache(
                agent_name="news-agent",
                event_type="news_sentiment",
                timestamp=t_cache,
                value_json={"sentiment": "BULLISH"},
            )
        )

        # B. Seeding Memory Event at index 150
        t_memory = start_time + timedelta(minutes=150 * 15)
        db.add(
            AgentMemoryEvent(
                agent_name="news-agent",
                event_type="news_sentiment",
                key="latest_analysis",
                value_json={"sentiment": "BEARISH"},
                created_at=t_memory,
            )
        )

        db.commit()
    finally:
        db.close()


def test_dataset_pipeline_feature_engineering_and_leakage():
    client, TestingSession = make_test_client()
    start_time = datetime.now(UTC) - timedelta(days=6)

    # Override build_dataset db session creation to use our TestingSession engine
    import scripts.build_dataset

    old_session = scripts.build_dataset.SessionLocal
    scripts.build_dataset.SessionLocal = TestingSession

    try:
        # Seed 800 snapshots
        seed_mock_history(TestingSession, start_time, count=800)

        # 1. Run build_dataset
        df = build_dataset(version="test_v1", dry_run=True)

        assert not df.empty
        assert "bank_spread_percent" in df.columns
        assert "xag_return_15m" in df.columns
        assert "news_sentiment_score" in df.columns
        assert "profitable_after_costs_3d" in df.columns
        assert "max_drawdown_3d" in df.columns

        # Test bank_spread_percent fallback calculation
        # First half has spread_percent = 1.0
        assert df.loc[0, "bank_spread_percent"] == 1.0
        # Second half fallback: (buy_price - sell_price) / mid_price * 100
        # buy = mid * 1.005, sell = mid * 0.995 -> spread_pct = (0.01 * mid) / mid * 100 = 1.0
        assert np.isclose(df.loc[450, "bank_spread_percent"], 1.0)

        # Test sentiment mapping
        # Index 0 to 99: default 0.0
        assert df.loc[0, "news_sentiment_score"] == 0.0
        # Index 100 to 149: BULLISH (1.0)
        assert df.loc[101, "news_sentiment_score"] == 1.0
        # Index 150 onwards: BEARISH (-1.0)
        assert df.loc[151, "news_sentiment_score"] == -1.0

        # Test max drawdown label at step 190
        # Price at index 200 drops to 30.0
        # Index 190 mid_price is around 20.0 + 190 * 0.1 = 39.0
        # Min price in the future 3 days (288 intervals) includes index 200 (drop to 30.0)
        # So drawdown = (39.0 - 30.0) / 39.0 = 0.23 (23%)
        assert df.loc[190, "max_drawdown_3d"] > 0.15

        # 2. Strict Zero-Leakage Test
        # Run build_dataset with all data, collect features for step 120
        feat_full = df.loc[
            120,
            [
                "bank_spread_percent",
                "xag_return_15m",
                "xag_return_1h",
                "xag_return_24h",
                "volatility_24h",
                "volatility_7d",
                "xau_xag_ratio",
                "news_sentiment_score",
            ],
        ].to_dict()

        # Wipe database completely, reseed only up to step 120
        db = TestingSession()
        try:
            db.query(PriceSnapshot).filter(
                PriceSnapshot.observed_at > start_time + timedelta(minutes=120 * 15)
            ).delete()
            db.query(RawFxRate).filter(RawFxRate.observed_at > start_time + timedelta(minutes=120 * 15)).delete()
            db.query(TechnicalIndicator).filter(
                TechnicalIndicator.bar_timestamp > start_time + timedelta(minutes=120 * 15)
            ).delete()
            db.query(AgentMemoryEvent).filter(
                AgentMemoryEvent.created_at > start_time + timedelta(minutes=120 * 15)
            ).delete()
            db.commit()
        finally:
            db.close()

        df_restricted = build_dataset(version="test_v2", dry_run=True, drop_unlabeled=False)
        feat_restricted = df_restricted.loc[
            120,
            [
                "bank_spread_percent",
                "xag_return_15m",
                "xag_return_1h",
                "xag_return_24h",
                "volatility_24h",
                "volatility_7d",
                "xau_xag_ratio",
                "news_sentiment_score",
            ],
        ].to_dict()

        # Verify that features in restricted dataset are EXACTLY IDENTICAL to full dataset
        for k in feat_full:
            assert np.isclose(feat_full[k], feat_restricted[k], rtol=1e-5), f"Feature leakage detected on {k}!"

        print("Strict zero-leakage feature verification passed!")

    finally:
        scripts.build_dataset.SessionLocal = old_session


def test_dataset_api_endpoints():
    client, TestingSession = make_test_client()

    # 1. Unauthenticated checks
    assert client.post("/datasets/build").status_code == 401
    assert client.get("/datasets/list").status_code == 401

    # 2. Build dataset in background (authorized)
    # Patch actual build_dataset function to avoid executing disk writes in tests
    import scripts.build_dataset

    old_session = scripts.build_dataset.SessionLocal
    scripts.build_dataset.SessionLocal = TestingSession

    try:
        start_time = datetime.now(UTC) - timedelta(days=6)
        seed_mock_history(TestingSession, start_time, count=100)

        # Trigger background task
        response = client.post("/datasets/build?version=99.0.0", headers={"X-Agent-Token": "test_token"})
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        assert "99.0.0" in response.json()["message"]

        # 3. List datasets
        # Create a mock datasets folder under data/datasets to test list functionality
        import scripts.build_dataset

        root_path = scripts.build_dataset.root_path
        datasets_dir = os.path.join(root_path, "data", "datasets", "v99.0.0")
        os.makedirs(datasets_dir, exist_ok=True)

        mock_meta = {
            "version": "99.0.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "row_count": 50,
            "feature_list": ["feat1"],
            "label_list": ["label1"],
        }
        with open(os.path.join(datasets_dir, "metadata.json"), "w") as f:
            json.dump(mock_meta, f)

        # Get list
        list_response = client.get("/datasets/list", headers={"X-Agent-Token": "test_token"})
        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data) >= 1
        assert any(d["version"] == "99.0.0" for d in data)

        # Clean up mock directories
        shutil.rmtree(os.path.dirname(datasets_dir), ignore_errors=True)

    finally:
        scripts.build_dataset.SessionLocal = old_session
