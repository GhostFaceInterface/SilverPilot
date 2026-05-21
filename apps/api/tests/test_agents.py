import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta

from app.agents.news import run_news_sentiment_analysis
from app.models import RawNews, AgentMemoryEvent, CollectorRun
from app.core.config import get_settings


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
