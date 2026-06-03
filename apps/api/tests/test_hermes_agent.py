import pytest
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.core.config import get_settings
from app.agents.hermes import run_hermes_sentiment_analysis
from app.services.strategy import StrategyRunner
from app.models import RawNews, AgentMemoryEvent, CollectorRun


@pytest.mark.anyio
async def test_hermes_sentiment_calculation_formula(db_session):
    """
    Verifies that the multi-aspect weighted score calculation is mathematically correct:
    - Article 1: Kitco (Global Authority, weight = 0.5), BULLISH (+1), relevance = 0.8, speculation = 0.2.
      Unweighted = 1 * (1 - 0.2) * 0.8 = 0.64. Weighted = 0.64 * 0.5 = 0.32.
    - Article 2: GCM (Local Expert, weight = 0.3), BEARISH (-1), relevance = 0.9, speculation = 0.1.
      Unweighted = -1 * (1 - 0.1) * 0.9 = -0.81. Weighted = -0.81 * 0.3 = -0.243.
    - Article 3: Investing (Local Forum, weight = 0.2), NEUTRAL (0), relevance = 0.5, speculation = 0.5.
      Unweighted = 0. Weighted = 0.

    Total Weighted Score = 0.32 + (-0.243) + 0 = 0.077.
    Total Source Weight = 0.5 + 0.3 + 0.2 = 1.0.
    Final Score = 0.077 / 1.0 = 0.077.
    """
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"
    settings.weight_global_authority = Decimal("0.5")
    settings.weight_local_expert = Decimal("0.3")
    settings.weight_local_forum = Decimal("0.2")

    # Add dummy collector run
    run = CollectorRun(
        collector_name="hermes-test-collector",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    # Add RawNews
    news1 = RawNews(
        collector_run_id=run.id,
        source="kitco-rss",
        title="Good Kitco News",
        url="http://example.com/1",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
        raw_payload_hash="h1",
        parser_version="1.0",
    )
    news2 = RawNews(
        collector_run_id=run.id,
        source="gcm-yatirim",
        title="Bad GCM News",
        url="http://example.com/2",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        raw_payload_hash="h2",
        parser_version="1.0",
    )
    news3 = RawNews(
        collector_run_id=run.id,
        source="investing",
        title="Neutral Investing News",
        url="http://example.com/3",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=3),
        raw_payload_hash="h3",
        parser_version="1.0",
    )
    db_session.add_all([news1, news2, news3])
    db_session.commit()

    # Mock DeepSeek API response corresponding to the articles
    mock_llm_json = json.dumps(
        [
            {"title": "Good Kitco News", "sentiment": "BULLISH", "relevance": 0.8, "speculation": 0.2},
            {"title": "Bad GCM News", "sentiment": "BEARISH", "relevance": 0.9, "speculation": 0.1},
            {"title": "Neutral Investing News", "sentiment": "NEUTRAL", "relevance": 0.5, "speculation": 0.5},
        ]
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": mock_llm_json,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
        }
        mock_post.return_value = mock_response

        # Execute
        event = await run_hermes_sentiment_analysis(db_session)

        # Assertions
        assert event is not None
        assert event.agent_name == "hermes-agent"
        assert event.event_type == "hermes_sentiment"
        assert event.key == "latest_analysis"

        val = event.value_json
        assert abs(val["score"] - 0.077) < 1e-5
        assert val["sentiment"] == "NEUTRAL"  # 0.077 is between -0.45 and 0.15
        assert len(val["articles"]) == 3

        # Verify specific details of Article 1
        art1 = val["articles"][0]
        assert art1["title"] == "Good Kitco News"
        assert art1["source"] == "kitco-rss"
        assert art1["sentiment"] == "BULLISH"
        assert abs(art1["article_score"] - 0.32) < 1e-5


@pytest.mark.anyio
async def test_hermes_veto_threshold_behavior(db_session):
    """
    Verifies that StrategyRunner correctly vetoes BUY to HOLD when the latest
    Hermes score is less than the hermes_veto_threshold.
    """
    settings = get_settings()
    settings.hermes_veto_threshold = Decimal("-0.45")

    # Clear previous hermes events
    db_session.query(AgentMemoryEvent).filter_by(agent_name="hermes-agent").delete()
    db_session.commit()

    # Scenario A: Hermes score is -0.5 (below veto threshold -0.45)
    event_veto = AgentMemoryEvent(
        agent_name="hermes-agent",
        event_type="hermes_sentiment",
        key="latest_analysis",
        value_json={"score": -0.5, "sentiment": "BEARISH"},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event_veto)
    db_session.commit()

    # Veto should trigger! Action BUY should become HOLD with AGENT_VETO_HERMES_BEARISH_NEWS
    action, reason = StrategyRunner.apply_agent_filters("BUY", "BULLISH", "APPROVED", db=db_session)
    assert action == "HOLD"
    assert reason == "AGENT_VETO_HERMES_BEARISH_NEWS"

    # Scenario B: Hermes score is -0.4 (above veto threshold -0.45)
    # We add a newer event to ensure order_by(desc(id)) catches it
    event_ok = AgentMemoryEvent(
        agent_name="hermes-agent",
        event_type="hermes_sentiment",
        key="latest_analysis",
        value_json={"score": -0.4, "sentiment": "BEARISH"},
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    db_session.add(event_ok)
    db_session.commit()

    # Veto should NOT trigger!
    action, reason = StrategyRunner.apply_agent_filters("BUY", "BULLISH", "APPROVED", db=db_session)
    assert action == "BUY"
    assert reason == ""


@pytest.mark.anyio
async def test_run_hermes_sentiment_analysis_empty_db(db_session):
    """
    Verifies the fallback behavior when the database is empty.
    """
    # Clear all RawNews
    db_session.query(RawNews).delete()
    db_session.commit()

    with patch("app.collectors.public_sources.collect_rss_news", return_value=(MagicMock(), 0)):
        event = await run_hermes_sentiment_analysis(db_session)
    assert event is not None
    assert event.agent_name == "hermes-agent"
    assert event.value_json["score"] == 0.0
    assert event.value_json["sentiment"] == "NEUTRAL"
    assert "No news articles found" in event.value_json["summary_markdown"]


@pytest.mark.anyio
async def test_hermes_weekend_telegram_dispatch_success(db_session):
    from app.core.config import get_settings
    from app.models import RawNews, CollectorRun

    settings = get_settings()
    settings.telegram_bot_token = "mock_token"
    settings.telegram_chat_id = "123456"

    # Add dummy collector run & RawNews
    run = CollectorRun(
        collector_name="hermes-test",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    news = RawNews(
        collector_run_id=run.id,
        source="kitco-rss",
        title="Silver prices skyrocket!",
        url="http://example.com/1",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
        raw_payload_hash="h_integration",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    mock_llm_json = json.dumps(
        [{"title": "Silver prices skyrocket!", "sentiment": "BULLISH", "relevance": 0.9, "speculation": 0.1}]
    )

    with (
        patch("httpx.AsyncClient.post") as mock_post,
        patch("app.risk.service.is_comex_weekend", return_value=True),
        patch("app.agents.hermes.send_telegram_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = lambda: {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": mock_llm_json,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
        }
        mock_post.return_value = mock_response

        # Execute agent analysis
        event = await run_hermes_sentiment_analysis(db_session)

        assert event is not None
        # Assert send_telegram_message was successfully called and fully awaited
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert kwargs["bot_token"] == "mock_token"
        assert kwargs["chat_id"] == "123456"
        assert "SilverPilot Hafta Sonu Nöbetçi Raporu" in kwargs["text"]
        assert "Genel Sentiment Skoru" in kwargs["text"]


@pytest.mark.anyio
async def test_hermes_weekend_telegram_dispatch_failure_resilience(db_session):
    from app.core.config import get_settings
    from app.models import RawNews, CollectorRun

    settings = get_settings()
    settings.telegram_bot_token = "mock_token"
    settings.telegram_chat_id = "123456"

    # Clear previous events
    db_session.query(AgentMemoryEvent).filter_by(agent_name="hermes-agent").delete()
    db_session.commit()

    # Add dummy RawNews
    run = CollectorRun(
        collector_name="hermes-test",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    news = RawNews(
        collector_run_id=run.id,
        source="kitco-rss",
        title="Silver prices skyrocket!",
        url="http://example.com/1",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
        raw_payload_hash="h_integration2",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    mock_llm_json = json.dumps(
        [{"title": "Silver prices skyrocket!", "sentiment": "BULLISH", "relevance": 0.9, "speculation": 0.1}]
    )

    with (
        patch("httpx.AsyncClient.post") as mock_post,
        patch("app.risk.service.is_comex_weekend", return_value=True),
        patch("app.agents.hermes.send_telegram_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = lambda: {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": mock_llm_json,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
        }
        mock_post.return_value = mock_response

        # Mock send_telegram_message to raise an error
        mock_send.side_effect = Exception("Telegram Connection Failure")

        # Execute
        event = await run_hermes_sentiment_analysis(db_session)

        # Verify it did not crash and saved the event cleanly in database
        assert event is not None
        assert event.agent_name == "hermes-agent"
        assert event.value_json["score"] > 0.0
        mock_send.assert_called_once()


@pytest.mark.anyio
async def test_hermes_llm_failure_graceful_recovery(db_session):
    from app.models import RawNews, CollectorRun

    db_session.query(RawNews).delete()
    db_session.commit()

    run = CollectorRun(
        collector_name="hermes-test",
        source="test",
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    news = RawNews(
        collector_run_id=run.id,
        source="kitco-rss",
        title="Silver news",
        url="http://example.com/1",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
        raw_payload_hash="h_fail",
        parser_version="1.0",
    )
    db_session.add(news)
    db_session.commit()

    with patch("app.llm.gateway.DeepSeekGateway.generate_completion", side_effect=RuntimeError("LLM API Timeout")):
        event = await run_hermes_sentiment_analysis(db_session)

        assert event is not None
        assert event.agent_name == "hermes-agent"
        assert event.value_json["score"] == 0.0
        assert event.value_json["sentiment"] == "NEUTRAL"
        assert "LLM call failed" in event.value_json["summary_markdown"]
