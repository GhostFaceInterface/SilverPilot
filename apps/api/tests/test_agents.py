import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta

from app.agents.news import run_news_sentiment_analysis
from app.agents.risk import run_signal_critique
from app.models import RawNews, AgentMemoryEvent, CollectorRun, Signal, TechnicalIndicator, Portfolio, PortfolioSnapshot, Asset, PriceSnapshot, Report, PaperTrade
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



