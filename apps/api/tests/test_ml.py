import os
import sys
import pickle
import shutil
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Sys path setup to import scripts and app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from app.core.db import Base, get_db
from app.main import create_app
from app.models import (
    Asset,
    PriceSnapshot,
    RawFxRate,
    RawBankPrice,
    RawGlobalPrice,
    TechnicalIndicator,
    HistoricalAgentCache,
    AgentMemoryEvent,
    Portfolio,
    RiskDecision
)
from app.core.config import get_settings, Settings
from app.ml.inference import extract_live_features, predict_profitability, load_model
from app.risk.service import evaluate_paper_trade_risk, TradeAmounts
from app.schemas.paper_trading import PaperTradeRequest


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
        
        portfolio = Portfolio(
            name="default-paper",
            initial_cash=Decimal("1000.00"),
            cash_balance=Decimal("1000.00"),
            base_currency="USD"
        )
        db.add(portfolio)
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
        return Settings(
            agent_api_token="test_token",
            risk_ml_model_enabled=True,
            risk_ml_min_probability=0.50,
            risk_ml_model_path="data/models/champion_model.pkl"
        )
    app.dependency_overrides[get_settings] = override_get_settings

    return TestClient(app), TestingSession


def seed_mock_history(TestingSession, start_time: datetime, count: int = 100):
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
            details_json={}
        )
        db.add(run)
        db.flush()
        
        for i in range(count):
            t = start_time + timedelta(minutes=i * 15)
            mid = 20.0 + i * 0.05
            buy_price = mid * 1.002
            sell_price = mid * 0.998
            
            db.add(PriceSnapshot(
                asset_id=asset.id,
                source="kuveyt_public_silver",
                buy_price=Decimal(str(buy_price)),
                sell_price=Decimal(str(sell_price)),
                mid_price=Decimal(str(mid)),
                currency="TRY",
                spread_absolute=Decimal(str(buy_price - sell_price)),
                spread_percent=Decimal("0.4"),
                observed_at=t,
                is_degraded=False
            ))
            
            # Seed RawFxRates, RawBankPrice, and RawGlobalPrice every hour (4 intervals)
            if i % 4 == 0:
                db.add(RawFxRate(
                    collector_run_id=run.id,
                    source="tcmb",
                    base_currency="USD",
                    quote_currency="TRY",
                    rate=Decimal(str(32.0 + i * 0.01)),
                    observed_at=t,
                    fetched_at=t,
                    raw_payload_hash=f"fx-hash-{i}",
                    parser_version="1",
                    payload_json={}
                ))
                
                db.add(RawBankPrice(
                    collector_run_id=run.id,
                    asset_id=asset.id,
                    source="kuveyt_public_silver",
                    buy_price=Decimal(str(buy_price)),
                    sell_price=Decimal(str(sell_price)),
                    currency="TRY",
                    observed_at=t,
                    fetched_at=t,
                    raw_payload_hash=f"bank-hash-{i}",
                    parser_version="1",
                    payload_json={}
                ))
                
                db.add(RawGlobalPrice(
                    collector_run_id=run.id,
                    asset_id=asset.id,
                    source="gold_api_xag_usd",
                    buy_price=Decimal(str(buy_price / 32.0)),
                    sell_price=Decimal(str(sell_price / 32.0)),
                    currency="USD",
                    observed_at=t,
                    fetched_at=t,
                    raw_payload_hash=f"global-hash-{i}",
                    parser_version="1",
                    payload_json={}
                ))
                
            # Seed TechnicalIndicator every hour (4 intervals)
            if i % 4 == 0:
                db.add(TechnicalIndicator(
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
                    xau_xag_ratio=Decimal(str(80.0 + i * 0.05))
                ))
        
        # News Sentiment बुलिश/Bearish
        t_cache = start_time + timedelta(minutes=50 * 15)
        db.add(HistoricalAgentCache(
            agent_name="news-agent",
            event_type="news_sentiment",
            timestamp=t_cache,
            value_json={"sentiment": "BULLISH"}
        ))

        db.commit()
    finally:
        db.close()


def test_live_feature_extraction_accuracy():
    client, TestingSession = make_test_client()
    db = TestingSession()
    start_time = datetime.now(UTC) - timedelta(days=5)

    try:
        seed_mock_history(TestingSession, start_time, count=100)
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one()
        
        # Run live extraction
        df_feat = extract_live_features(db, asset.id)
        
        assert df_feat is not None
        assert df_feat.shape == (1, 11)
        
        # Verify specific feature definitions and math boundaries
        assert float(df_feat.loc[0, "bank_spread_percent"]) == 0.4
        assert float(df_feat.loc[0, "news_sentiment_score"]) == 1.0  # BULLISH sentiment
        assert float(df_feat.loc[0, "xau_xag_ratio"]) > 0
        assert float(df_feat.loc[0, "hour_of_day"]) >= 0 and float(df_feat.loc[0, "hour_of_day"]) < 24
        assert float(df_feat.loc[0, "day_of_week"]) >= 0 and float(df_feat.loc[0, "day_of_week"]) < 7
        
        # Verify volatility returns non-NaN values
        assert float(df_feat.loc[0, "volatility_24h"]) >= 0.0
        assert float(df_feat.loc[0, "volatility_7d"]) >= 0.0
    finally:
        db.close()


def test_graceful_fallback_when_model_missing(monkeypatch):
    client, TestingSession = make_test_client()
    db = TestingSession()
    start_time = datetime.now(UTC) - timedelta(days=2)

    try:
        seed_mock_history(TestingSession, start_time, count=20)
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one()
        
        # Mock settings to point to a non-existent model file
        monkeypatch.setattr("app.ml.inference.get_settings", lambda: Settings(
            risk_ml_model_enabled=True,
            risk_ml_model_path="data/models/does_not_exist_xyz.pkl",
            risk_ml_min_probability=0.50
        ))
        
        # Cache reset to force reload attempt
        import app.ml.inference
        app.ml.inference._MODEL_LOADED = False
        app.ml.inference._MODEL_CACHE = None
        
        # Call predict profitability
        proba = predict_profitability(db, asset.id)
        
        # Must return None (bypass) instead of throwing FileNotFoundError / crashing
        assert proba is None
        
        # Check that risk evaluate allows the trade (graceful fallback)
        portfolio = db.query(Portfolio).one()
        amounts = TradeAmounts(
            quantity=Decimal("10"),
            price=Decimal("20.0"),
            gross_amount=Decimal("200.0"),
            net_amount=Decimal("201.0")
        )
        request = PaperTradeRequest(
            asset_symbol="XAG",
            action="paper_buy",
            buy_price=Decimal("20.10"),
            sell_price=Decimal("19.90"),
            quantity=Decimal("10"),
            expected_exit_price=Decimal("25.0")
        )
        
        # Mock class for position Protocol
        class MockPosition:
            quantity = Decimal("0")

        decision = evaluate_paper_trade_risk(
            db,
            request=request,
            portfolio=portfolio,
            asset=asset,
            position=MockPosition(),
            amounts=amounts
        )
        
        # Fallback bypass means the trade passes the ML check and is "allow" (or blocked by other normal rules like spread)
        # Here we verify it does not fail with ML exceptions.
        assert decision.decision in ("allow", "blocked")
        assert decision.reason_code != "ML_UNPROFITABLE_PREDICTION"
    finally:
        db.close()


def test_ml_risk_blocking_on_unprofitable_prediction(monkeypatch):
    client, TestingSession = make_test_client()
    db = TestingSession()
    start_time = datetime.now(UTC) - timedelta(days=2)

    try:
        seed_mock_history(TestingSession, start_time, count=20)
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one()
        
        # Mock a dummy model that predicts a very low profitability probability (e.g. 0.15)
        class MockLGBMModel:
            def predict_proba(self, X):
                return np.array([[0.85, 0.15]])  # 15% probability of profitable
                
        # Force the cached model loader to return our mock model
        import app.ml.inference
        app.ml.inference._MODEL_LOADED = True
        app.ml.inference._MODEL_CACHE = MockLGBMModel()
        
        # Set mock settings consistently across all active modules
        mock_settings = Settings(
            risk_ml_model_enabled=True,
            risk_ml_min_probability=0.50,
            risk_ml_model_path="dummy_path.pkl",
            risk_max_spread_percent=Decimal("5.0"),
            risk_data_stale_after_minutes=9999,
            global_xag_freshness_minutes=9999,
            risk_max_daily_loss_usd=Decimal("9999.0"),
            risk_max_weekly_loss_usd=Decimal("9999.0"),
            risk_max_24h_volatility_percent=Decimal("99.0"),
            risk_max_7d_volatility_percent=Decimal("99.0"),
            risk_fomo_lookback_minutes=9999,
            risk_fomo_rise_percent=Decimal("99.0"),
            risk_min_expected_net_gain_percent=Decimal("0.0")
        )
        monkeypatch.setattr("app.ml.inference.get_settings", lambda: mock_settings)
        monkeypatch.setattr("app.risk.service.get_settings", lambda: mock_settings)
        monkeypatch.setattr("app.collectors.service.get_settings", lambda: mock_settings)
        
        # 1. Check prediction
        proba = predict_profitability(db, asset.id)
        assert proba == 0.15
        
        # 2. Check risk block execution
        portfolio = db.query(Portfolio).one()
        amounts = TradeAmounts(
            quantity=Decimal("10"),
            price=Decimal("20.0"),
            gross_amount=Decimal("200.0"),
            net_amount=Decimal("201.0")
        )
        request = PaperTradeRequest(
            asset_symbol="XAG",
            action="paper_buy",
            buy_price=Decimal("20.04"),
            sell_price=Decimal("19.96"),
            quantity=Decimal("10"),
            expected_exit_price=Decimal("25.0")
        )
        
        class MockPosition:
            quantity = Decimal("0")

        decision = evaluate_paper_trade_risk(
            db,
            request=request,
            portfolio=portfolio,
            asset=asset,
            position=MockPosition(),
            amounts=amounts
        )
        
        # Must be blocked by ML prediction
        print(decision.details_json)
        assert decision.decision == "blocked"
        assert decision.reason_code == "ML_UNPROFITABLE_PREDICTION"
        assert decision.details_json["predicted_probability"] == "0.1500"
        
    finally:
        db.close()
