import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta

from app.agents.news import run_news_sentiment_analysis
from app.agents.risk import run_signal_critique
from app.models import (
    RawNews,
    AgentMemoryEvent,
    CollectorRun,
    Signal,
    TechnicalIndicator,
    Portfolio,
    PortfolioSnapshot,
    Asset,
    PriceSnapshot,
    Report,
    PaperTrade,
)
from app.core.config import get_settings
from decimal import Decimal


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_news_agent_analysis_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Setup dummy collector run
    run = CollectorRun(
        collector_name="news-test-collector",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Add mock RawNews in the last 24 hours
    news = RawNews(
        collector_run_id=run.id,
        source="test-source",
        title="Silver prices skyrocket on supply deficit",
        url="http://example.com/silver",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        raw_payload_hash="hash123",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    # Mock HTTP response from DeepSeekGateway
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"sentiment": "BULLISH", "confidence": 0.95, "summary_markdown": "Silver prices are set to rise due to supply deficit."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 150,
            "total_tokens": 250,
        },
    }
    mock_post.return_value = mock_response

    # Run news analysis
    event = await run_news_sentiment_analysis(db_session)

    assert event is not None
    assert event.agent_name == "news-agent"
    assert event.event_type == "news_sentiment"
    assert event.key == "latest_analysis"
    assert event.value_json["sentiment"] == "BULLISH"
    assert event.value_json["confidence"] == 0.95
    assert event.value_json["summary_markdown"] == "Silver prices are set to rise due to supply deficit."
    assert "analyzed_at" in event.value_json

    # Check database persistence
    saved_event = db_session.query(AgentMemoryEvent).filter_by(agent_name="news-agent").first()
    assert saved_event is not None
    assert saved_event.id == event.id


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_news_agent_fallback_to_latest_10(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Setup dummy collector run
    run = CollectorRun(
        collector_name="news-test-collector",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Add old news (more than 24 hours ago, e.g., 2 days ago)
    old_news = RawNews(
        collector_run_id=run.id,
        source="old-source",
        title="Old silver article",
        url="http://example.com/old",
        fetched_at=datetime.now(timezone.utc) - timedelta(days=2),
        raw_payload_hash="oldhash",
        parser_version="1.0",
    )
    db_session.add(old_news)
    db_session.commit()

    # Mock HTTP response from DeepSeekGateway
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '```json\n{"sentiment": "NEUTRAL", "confidence": 0.6, "summary_markdown": "Market consolidated in high volume."}\n```',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 50,
        },
    }
    mock_post.return_value = mock_response

    # Run news analysis
    event = await run_news_sentiment_analysis(db_session)

    assert event is not None
    assert event.value_json["sentiment"] == "NEUTRAL"
    assert event.value_json["confidence"] == 0.6
    assert event.value_json["summary_markdown"] == "Market consolidated in high volume."


@pytest.mark.anyio
async def test_news_agent_empty_database(db_session):
    # Run news analysis with empty database (should not make HTTP calls and immediately return fallback neutral event)
    with patch("app.collectors.public_sources.collect_rss_news", return_value=(None, 0)):
        event = await run_news_sentiment_analysis(db_session)

    assert event is not None
    assert event.value_json["sentiment"] == "NEUTRAL"
    assert event.value_json["confidence"] == 0.0
    assert "No recent news articles found" in event.value_json["summary_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_risk_agent_critique_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, PriceSnapshot, TechnicalIndicator, Portfolio, PortfolioSnapshot, Signal
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    tech_ind = TechnicalIndicator(
        price_snapshot_id=price_snap.id,
        bar_timestamp=datetime.now(timezone.utc),
        timeframe="1H",
        rsi_14=Decimal("28.5"),
        close_usd_oz=Decimal("25.0"),
    )
    db_session.add(tech_ind)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        indicator_id=tech_ind.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
        details_json={},
    )
    db_session.add(signal)
    db_session.commit()

    portfolio = Portfolio(
        name="test-portfolio",
        base_currency="USD",
        initial_cash=Decimal("10000.0"),
        cash_balance=Decimal("10000.0"),
    )
    db_session.add(portfolio)
    db_session.commit()

    portfolio_snap = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        cash_balance=Decimal("10000.0"),
        asset_quantity=Decimal("0.0"),
        portfolio_value=Decimal("10000.0"),
        realized_pnl=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(portfolio_snap)
    db_session.commit()

    # Mock HTTP response from DeepSeekGateway
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '```json\n{"decision": "APPROVED", "confidence": 0.9, "critique_markdown": "Highly favorable buy setup."}\n```',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 80,
        },
    }
    mock_post.return_value = mock_response

    # Run critique
    event = await run_signal_critique(db_session, signal.id)

    assert event is not None
    assert event.agent_name == "risk-agent"
    assert event.event_type == "signal_critique"
    assert event.key == f"critique_signal_{signal.id}"
    assert event.value_json["decision"] == "APPROVED"
    assert event.value_json["confidence"] == 0.9
    assert event.value_json["critique_markdown"] == "Highly favorable buy setup."
    assert event.value_json["signal_id"] == signal.id
    assert "analyzed_at" in event.value_json

    # Check database persistence
    saved_event = db_session.query(AgentMemoryEvent).filter_by(agent_name="risk-agent").first()
    assert saved_event is not None
    assert saved_event.id == event.id


@pytest.mark.anyio
async def test_risk_agent_empty_database(db_session):
    # Running critique with empty database should gracefully bypass LLM calling and create approved critique event.
    event = await run_signal_critique(db_session, signal_id=None)

    assert event is not None
    assert event.agent_name == "risk-agent"
    assert event.event_type == "signal_critique"
    assert event.key == "critique_signal_none"
    assert event.value_json["decision"] == "APPROVED"
    assert event.value_json["confidence"] == 1.0
    assert "No signals exist in the database" in event.value_json["critique_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_report_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, Portfolio, PortfolioSnapshot, PaperTrade
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    portfolio = Portfolio(
        name="test-portfolio",
        base_currency="USD",
        initial_cash=Decimal("10000.0"),
        cash_balance=Decimal("9500.0"),
    )
    db_session.add(portfolio)
    db_session.commit()

    portfolio_snap = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        cash_balance=Decimal("9500.0"),
        asset_quantity=Decimal("20.0"),
        portfolio_value=Decimal("10000.0"),
        realized_pnl=Decimal("100.0"),
        unrealized_pnl=Decimal("-50.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(portfolio_snap)
    db_session.commit()

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action="BUY",
        quantity=Decimal("20.0"),
        price=Decimal("25.0"),
        gross_amount=Decimal("500.0"),
        fees=Decimal("0.0"),
        taxes=Decimal("0.0"),
        net_amount=Decimal("500.0"),
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(trade)
    db_session.commit()

    # Mock HTTP response from DeepSeekGateway
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "# Daily Performance Report\nGreat performance!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 80,
        },
    }
    mock_post.return_value = mock_response

    from app.agents.report import run_daily_performance_report

    report = await run_daily_performance_report(db_session)

    assert report is not None
    assert report.report_type == "daily"
    assert report.payload_json["portfolio_value"] == 10000.0
    assert report.payload_json["cash_balance"] == 9500.0
    assert report.payload_json["trades_count"] == 1
    assert "Great performance!" in report.payload_json["report_content"]

    # Check database persistence
    saved_report = db_session.query(Report).filter_by(report_type="daily").first()
    assert saved_report is not None
    assert saved_report.id == report.id


@pytest.mark.anyio
async def test_report_agent_empty_database(db_session):
    from app.agents.report import run_daily_performance_report

    # Run with empty database (should gracefully fallback without LLM calling)
    report = await run_daily_performance_report(db_session)

    assert report is not None
    assert report.report_type == "daily"
    assert report.payload_json["portfolio_value"] == 0.0
    assert report.payload_json["cash_balance"] == 0.0
    assert report.payload_json["trades_count"] == 0
    assert "No active portfolio data or snapshots found" in report.payload_json["report_content"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_news_agent_malformed_json_recovery(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Setup dummy collector run
    run = CollectorRun(
        collector_name="news-test-collector",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Add RawNews
    news = RawNews(
        collector_run_id=run.id,
        source="test-source",
        title="Silver news title",
        url="http://example.com/silver",
        fetched_at=datetime.now(timezone.utc),
        raw_payload_hash="hash",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    # Mock HTTP response with invalid JSON
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is completely malformed non-JSON data from LLM gateway.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        },
    }
    mock_post.return_value = mock_response

    event = await run_news_sentiment_analysis(db_session)
    assert event is not None
    assert event.value_json["sentiment"] == "NEUTRAL"
    assert event.value_json["confidence"] == 0.5
    assert "Failed to parse" in event.value_json["summary_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_risk_agent_malformed_json_recovery(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, PriceSnapshot, Signal
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
        details_json={},
    )
    db_session.add(signal)
    db_session.commit()

    # Mock HTTP response with invalid JSON
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Invalid response format",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        },
    }
    mock_post.return_value = mock_response

    event = await run_signal_critique(db_session, signal.id)
    assert event is not None
    assert event.value_json["decision"] == "APPROVED"
    assert event.value_json["confidence"] == 0.5
    assert "Failed to parse" in event.value_json["critique_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_risk_agent_degraded_state_missing_indicators(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, PriceSnapshot, Signal, Portfolio, PortfolioSnapshot
    # Do not add TechnicalIndicator! This simulates a missing indicator condition.
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
        details_json={},
    )
    db_session.add(signal)
    db_session.commit()

    portfolio = Portfolio(
        name="test-portfolio",
        base_currency="USD",
        initial_cash=Decimal("10000.0"),
        cash_balance=Decimal("10000.0"),
    )
    db_session.add(portfolio)
    db_session.commit()

    portfolio_snap = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        cash_balance=Decimal("10000.0"),
        asset_quantity=Decimal("0.0"),
        portfolio_value=Decimal("10000.0"),
        realized_pnl=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(portfolio_snap)
    db_session.commit()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"decision": "CAUTION", "confidence": 0.8, "critique_markdown": "Audit despite missing indicators"}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    event = await run_signal_critique(db_session, signal.id)
    assert event is not None
    assert event.value_json["decision"] == "CAUTION"
    assert event.value_json["confidence"] == 0.8
    assert "missing indicators" in event.value_json["critique_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_risk_agent_degraded_state_missing_portfolio_snapshot(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, PriceSnapshot, Signal
    # Do not add Portfolio Snapshot or Portfolio at all!
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
        details_json={},
    )
    db_session.add(signal)
    db_session.commit()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"decision": "APPROVED", "confidence": 0.9, "critique_markdown": "Passed despite missing portfolio snapshot"}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    event = await run_signal_critique(db_session, signal.id)
    assert event is not None
    assert event.value_json["decision"] == "APPROVED"
    assert event.value_json["confidence"] == 0.9
    assert "missing portfolio snapshot" in event.value_json["critique_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_strategy_risk_critique_hook_execution(mock_post, db_session):
    from app.services.strategy import trigger_risk_critique_hook

    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset, PriceSnapshot, Signal
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
        details_json={},
    )
    db_session.add(signal)
    db_session.commit()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"decision": "APPROVED", "confidence": 0.95, "critique_markdown": "Hook test pass"}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    event = await trigger_risk_critique_hook(db_session, signal_id=signal.id)
    assert event is not None
    assert event.event_type == "signal_critique"
    assert event.value_json["decision"] == "APPROVED"
    assert event.value_json["confidence"] == 0.95
    assert event.value_json["critique_markdown"] == "Hook test pass"


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_market_research_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock TechnicalIndicator & PriceSnapshot
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    tech_ind = TechnicalIndicator(
        price_snapshot_id=price_snap.id,
        bar_timestamp=datetime.now(timezone.utc),
        timeframe="1H",
        rsi_14=Decimal("35.0"),
    )
    db_session.add(tech_ind)
    db_session.commit()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"sentiment": "BULLISH", "confidence": 0.85, "summary_markdown": "Indicators are bullish."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    from app.agents.market_research import run_market_research_analysis

    event = await run_market_research_analysis(db_session)

    assert event is not None
    assert event.agent_name == "market-research-agent"
    assert event.event_type == "market_trend"
    assert event.value_json["sentiment"] == "BULLISH"
    assert event.value_json["confidence"] == 0.85


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_ml_analyst_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock Asset and PriceSnapshot so feature extraction succeeds
    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    price_snap_old = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("24.0"),
        sell_price=Decimal("24.0"),
        mid_price=Decimal("24.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(price_snap_old)

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    tech_ind = TechnicalIndicator(
        price_snapshot_id=price_snap.id,
        bar_timestamp=datetime.now(timezone.utc),
        timeframe="1H",
        rsi_14=Decimal("35.0"),
    )
    db_session.add(tech_ind)
    db_session.commit()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"recommendation": "APPROVE", "confidence": 0.9, "analysis_markdown": "ML predicts profitability."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    from app.agents.ml_analyst import run_ml_inference_critique

    event = await run_ml_inference_critique(db_session)

    assert event is not None
    assert event.agent_name == "ml-analyst-agent"
    assert event.event_type == "ml_analysis"
    assert event.value_json["recommendation"] == "APPROVE"


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_source_reliability_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add dummy collector runs
    run = CollectorRun(
        collector_name="fred_macro",
        source="fred-api",
        status="success",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"status": "healthy", "summary_markdown": "Data flows are perfect."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    from app.agents.source_reliability import run_source_reliability_analysis

    event = await run_source_reliability_analysis(db_session)

    assert event is not None
    assert event.agent_name == "source-reliability-agent"
    assert event.event_type == "source_reliability"
    assert event.value_json["status"] == "healthy"


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_postmortem_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Add mock blocked PaperTrade with valid Portfolio & Asset to satisfy foreign keys
    portfolio = Portfolio(
        name="test-portfolio",
        base_currency="USD",
        initial_cash=Decimal("10000.0"),
        cash_balance=Decimal("10000.0"),
    )
    db_session.add(portfolio)
    db_session.commit()

    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action="blocked",
        quantity=Decimal("10"),
        price=Decimal("25.0"),
        gross_amount=Decimal("250.0"),
        fees=Decimal("0.0"),
        taxes=Decimal("0.0"),
        net_amount=Decimal("250.0"),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"details_markdown": "# Postmortem Report\\n- Trade was blocked."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    from app.agents.postmortem import run_postmortem_analysis

    event = await run_postmortem_analysis(db_session)

    assert event is not None
    assert event.agent_name == "postmortem-agent"
    assert event.event_type == "postmortem_analysis"
    assert event.value_json["blocked_trades_count"] == 1


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_auditor_agent_success(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"audit_markdown": "# System Audit Report\\n- Budget healthy."}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    mock_post.return_value = mock_response

    from app.agents.auditor import run_system_audit

    event = await run_system_audit(db_session)

    assert event is not None
    assert event.agent_name == "auditor-agent"
    assert event.event_type == "system_audit"
    assert "Budget healthy" in event.value_json["audit_markdown"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_orchestrator_flow_and_conflict_resolution(mock_post, db_session):
    # Setup mock API key
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Set up necessary DB state so agents don't fallback to completely empty
    portfolio = Portfolio(
        name="default-paper",
        base_currency="USD",
        initial_cash=Decimal("10000.0"),
        cash_balance=Decimal("10000.0"),
    )
    db_session.add(portfolio)
    db_session.commit()

    asset = Asset(symbol="XAG", name="Silver", asset_type="precious_metal", is_active=True)
    db_session.add(asset)
    db_session.commit()

    run = CollectorRun(
        collector_name="news-test-collector",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    price_snap_old = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("24.0"),
        sell_price=Decimal("24.0"),
        mid_price=Decimal("24.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(price_snap_old)

    price_snap = PriceSnapshot(
        asset_id=asset.id,
        source="test-source",
        buy_price=Decimal("25.0"),
        sell_price=Decimal("25.0"),
        mid_price=Decimal("25.0"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(price_snap)
    db_session.commit()

    tech_ind = TechnicalIndicator(
        price_snapshot_id=price_snap.id,
        bar_timestamp=datetime.now(timezone.utc),
        timeframe="1H",
        rsi_14=Decimal("35.0"),
    )
    db_session.add(tech_ind)
    db_session.commit()

    signal = Signal(
        observed_at=datetime.now(timezone.utc),
        price_snapshot_id=price_snap.id,
        indicator_id=tech_ind.id,
        action="BUY",
        reason_code="RSI_OVERSOLD",
        price_usd_oz=Decimal("25.0"),
    )
    db_session.add(signal)
    db_session.commit()

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action="blocked",
        quantity=Decimal("10"),
        price=Decimal("25.0"),
        gross_amount=Decimal("250.0"),
        fees=Decimal("0.0"),
        taxes=Decimal("0.0"),
        net_amount=Decimal("250.0"),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()

    news = RawNews(
        collector_run_id=run.id,
        source="test-source",
        title="Silver prices skyrocket on supply deficit",
        url="http://example.com/silver",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        raw_payload_hash="hash123",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    # Mock multi-completion response generator: we will mock post responses sequentially.
    # 1. News agent call (BULLISH sentiment)
    # 2. Risk agent call (APPROVED decision)
    # 3. Market Research call (BEARISH sentiment) -> Contradiction!
    # 4. ML Analyst call (VETO recommendation) -> Contradiction!
    # 5. Source Reliability call
    # 6. Postmortem call
    # 7. Auditor call
    # 8. Supreme Arbiter resolution call (VETO resolution)

    responses = [
        # 1. News
        '{"sentiment": "BULLISH", "confidence": 0.9, "summary_markdown": "News is BULLISH."}',
        # 2. Risk
        '{"decision": "APPROVED", "confidence": 0.95, "critique_markdown": "Risk APPROVED."}',
        # 3. Market Research
        '{"sentiment": "BEARISH", "confidence": 0.8, "summary_markdown": "Market is BEARISH."}',
        # 4. ML Analyst
        '{"recommendation": "VETO", "confidence": 0.88, "analysis_markdown": "ML recommends VETO."}',
        # 5. Source Reliability
        '{"status": "healthy", "summary_markdown": "Sources healthy."}',
        # 6. Postmortem
        '{"details_markdown": "Postmortem details."}',
        # 7. Auditor
        '{"audit_markdown": "System audit."}',
        # 8. Supreme Arbiter Resolution
        '{"resolved_stance": "VETO", "confidence": 0.9, "resolution_markdown": "Supreme Arbiter resolved as VETO due to ML and Market Research contradictions."}',
    ]

    call_index = 0

    def mock_post_side_effect(*args, **kwargs):
        nonlocal call_index
        resp = AsyncMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None

        content = responses[min(call_index, len(responses) - 1)]
        call_index += 1

        resp.json = lambda: {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        return resp

    mock_post.side_effect = mock_post_side_effect

    from app.agents.orchestrator import run_multi_agent_analysis

    res = await run_multi_agent_analysis(db_session)

    assert res["status"] == "success"
    assert res["conflict_detected"] is True
    assert res["disagreement"] is not None
    assert res["resolution"] is not None

    # Verify disagreement persistence
    disag = db_session.query(AgentMemoryEvent).filter_by(id=res["disagreement"]).first()
    assert disag is not None
    assert disag.event_type == "agent_disagreement"

    # Verify resolution persistence
    resol = db_session.query(AgentMemoryEvent).filter_by(id=res["resolution"]).first()
    assert resol is not None
    assert resol.event_type == "disagreement_resolution"
    assert resol.value_json["resolved_stance"] == "VETO"
