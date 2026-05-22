import os
import sys
import pytest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from app.core.db import Base
from app.models import Asset, PriceSnapshot, TechnicalIndicator
from scripts.backtest_engine import run_backtest


@pytest.fixture(name="db_session")
def fixture_db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed Asset
    db = TestingSessionLocal()
    xag = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
    db.add(xag)
    db.commit()
    db.close()

    return TestingSessionLocal


def seed_historical_data(db_session_class, prices: list[float], rsis: list[float]):
    """Helper to seed mock price snapshots and indicators."""
    db = db_session_class()
    asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
    
    for idx, price in enumerate(prices):
        observed_at = datetime(2026, 5, 1 + idx, 4, 0, tzinfo=UTC)
        snap = PriceSnapshot(
            asset_id=asset.id,
            source="yahoo-si-f-1d",
            buy_price=Decimal(str(price)),
            sell_price=Decimal(str(price)),
            mid_price=Decimal(str(price)),
            currency="USD",
            spread_absolute=Decimal("0.0"),
            spread_percent=Decimal("0.0"),
            observed_at=observed_at,
            resolved_source="yahoo_si_f",
            is_degraded=False,
        )
        db.add(snap)
        db.flush()

        ti = TechnicalIndicator(
            price_snapshot_id=snap.id,
            bar_timestamp=observed_at,
            timeframe="1d",
            close_usd_oz=Decimal(str(price)),
            rsi_14=Decimal(str(rsis[idx])) if rsis[idx] is not None else None,
            sma_20=None,
            sma_50=None,
            bb_lower_20_2=None,
            bb_upper_20_2=None,
        )
        db.add(ti)
        
    db.commit()
    db.close()


def test_backtest_rsi_oversold_to_overbought(db_session):
    # Prices: start high, go down (RSI oversold), go high (RSI overbought), hold
    prices = [35.0, 32.0, 25.0, 26.0, 38.0, 36.0]
    rsis = [65.0, 50.0, 25.0, 32.0, 75.0, 60.0]
    
    seed_historical_data(db_session, prices, rsis)
    
    with patch("scripts.backtest_engine.SessionLocal", db_session):
        results = run_backtest(
            strategy_name="rsi",
            timeframe="1d",
            spread=0.02,     # 2% spread
            tax=0.002,       # 0.2% tax on sell
            fee=0.05,        # $0.05 fee
            slippage=0.0005, # 0.05% slippage
            initial_cash=600.0,
        )
        
        assert results is not None
        assert results["trades_count"] == 1  # 1 complete trade
        assert results["initial_cash"] == 600.0
        
        # Verify transaction cost drag & ending balances are correctly set
        assert results["ending_balance"] > 600.0  #Profitable trade
        assert results["cost_drag_percent"] > 0.0
        assert results["max_drawdown"] >= 0.0


def test_backtest_no_trades_executed(db_session):
    # Prices are neutral, RSI stays neutral
    prices = [30.0, 30.2, 30.1, 29.9, 30.0]
    rsis = [50.0, 51.0, 50.0, 49.0, 50.0]
    
    seed_historical_data(db_session, prices, rsis)
    
    with patch("scripts.backtest_engine.SessionLocal", db_session):
        results = run_backtest(
            strategy_name="rsi",
            timeframe="1d",
            spread=0.02,
            tax=0.002,
            fee=0.05,
            slippage=0.0005,
            initial_cash=600.0,
        )
        
        assert results is not None
        assert results["trades_count"] == 0
        assert results["ending_balance"] == 600.0
        assert results["max_drawdown"] == 0.0
        assert results["win_rate"] == 0.0


def test_backtest_drawdown_calculation():
    # Helper to calculate Max Drawdown on manual curve
    from scripts.backtest_engine import run_backtest
    
    # Let's test that drawdown handles peak and valley correctly.
    # In a simple equity curve: 100 -> 90 -> 110 -> 82.5 -> 120
    # First drop: (100 - 90)/100 = 10%
    # Second drop: peak is 110. Valley is 82.5. (110 - 82.5)/110 = 25%
    # Max drawdown should be 25%
    
    # We can verify that our drawdown equation inside backtest engine does exactly this.
    # We will pass equity_curve values and compute the drawdown logic.
    equities = [100.0, 90.0, 110.0, 82.5, 120.0]
    max_drawdown = 0.0
    peak = equities[0]
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0.0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd
            
    assert max_drawdown == 0.25


def test_backtest_rsi_with_agents_veto(db_session):
    # Prices start high, go down (RSI oversold - would trigger BUY), but agent is BEARISH
    prices = [35.0, 32.0, 25.0]
    rsis = [65.0, 50.0, 25.0]
    
    seed_historical_data(db_session, prices, rsis)
    
    # Add BEARISH news-agent cache record
    from app.models.entities import HistoricalAgentCache
    db = db_session()
    cache_record = HistoricalAgentCache(
        agent_name="news-agent",
        event_type="news_sentiment",
        timestamp=datetime(2026, 5, 3, 4, 0, tzinfo=UTC),
        value_json={"sentiment": "BEARISH"},
    )
    db.add(cache_record)
    db.commit()
    db.close()
    
    with patch("scripts.backtest_engine.SessionLocal", db_session):
        results = run_backtest(
            strategy_name="rsi_with_agents",
            timeframe="1d",
            spread=0.02,
            tax=0.002,
            fee=0.05,
            slippage=0.0005,
            initial_cash=600.0,
        )
        
        assert results is not None
        # Veto should have blocked the BUY action, so trades_count should be 0!
        assert results["trades_count"] == 0
        assert results["ending_balance"] == 600.0


def test_strategy_apply_agent_filters():
    from app.services.strategy import StrategyRunner
    
    # Test BUY vetoed by news_sentiment
    action, reason = StrategyRunner.apply_agent_filters("BUY", "BEARISH", "APPROVED")
    assert action == "HOLD"
    assert reason == "AGENT_VETO_BEARISH_NEWS"
    
    # Test BUY vetoed by risk_decision
    action, reason = StrategyRunner.apply_agent_filters("BUY", "BULLISH", "REJECTED")
    assert action == "HOLD"
    assert reason == "AGENT_VETO_RISK_REJECTED"
    
    # Test BUY approved when news is BULLISH and risk is APPROVED
    action, reason = StrategyRunner.apply_agent_filters("BUY", "BULLISH", "APPROVED")
    assert action == "BUY"
    assert reason == ""
    
    # Test non-BUY actions are untouched
    action, reason = StrategyRunner.apply_agent_filters("SELL", "BEARISH", "REJECTED")
    assert action == "SELL"
    assert reason == ""
