import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.core.config import get_settings
from app.models import LLMCallTrace
from app.llm.budget_guard import (
    get_daily_spent_usd,
    check_budget_limit,
    BudgetExceededError,
)
from app.llm.gateway import calculate_llm_cost, DeepSeekGateway


def test_calculate_llm_cost():
    # deepseek-chat pricing: input $0.14/1M, output $0.28/1M
    cost_chat = calculate_llm_cost("deepseek-chat", 1000, 2000)
    expected_chat = Decimal("1000") * Decimal("0.00000014") + Decimal("2000") * Decimal("0.00000028")
    assert cost_chat == expected_chat

    # deepseek-reasoner pricing: input $0.55/1M, output $2.19/1M
    cost_reasoner = calculate_llm_cost("deepseek-reasoner", 1000, 2000)
    expected_reasoner = Decimal("1000") * Decimal("0.00000055") + Decimal("2000") * Decimal("0.00000219")
    assert cost_reasoner == expected_reasoner

    # deepseek-v4-flash pricing: input $0.14/1M, output $0.28/1M
    cost_flash = calculate_llm_cost("deepseek-v4-flash", 1000, 2000)
    expected_flash = Decimal("1000") * Decimal("0.00000014") + Decimal("2000") * Decimal("0.00000028")
    assert cost_flash == expected_flash

    # deepseek-v4-pro pricing: input $0.435/1M, output $0.87/1M
    cost_pro = calculate_llm_cost("deepseek-v4-pro", 1000, 2000)
    expected_pro = Decimal("1000") * Decimal("0.000000435") + Decimal("2000") * Decimal("0.00000087")
    assert cost_pro == expected_pro

    # Fallback to deepseek-v4-flash when model not recognized
    cost_fallback = calculate_llm_cost("unknown-model", 1000, 2000)
    assert cost_fallback == expected_flash


def test_budget_guard_limits(db_session):
    settings = get_settings()
    settings.deepseek_daily_budget_usd = Decimal("1.00")

    # Start with empty db, spent should be 0
    assert get_daily_spent_usd(db_session) == Decimal("0.0")

    # Check limit succeeds
    assert check_budget_limit(db_session, Decimal("0.50")) is True

    # Record a mock call trace
    trace = LLMCallTrace(
        agent_name="test-agent",
        model_name="deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=2000,
        total_cost_usd=Decimal("0.80"),
        latency_ms=200,
        status="SUCCESS",
        prompt_raw="hello",
        response_raw="hi",
    )
    db_session.add(trace)
    db_session.commit()

    # Spent should now be 0.80
    assert get_daily_spent_usd(db_session) == Decimal("0.80")

    # Budget check with 0.10 additional cost should pass (0.80 + 0.10 = 0.90 < 1.00)
    assert check_budget_limit(db_session, Decimal("0.10")) is True

    # Budget check with 0.25 additional cost should fail (0.80 + 0.25 = 1.05 > 1.00)
    with pytest.raises(BudgetExceededError):
        check_budget_limit(db_session, Decimal("0.25"))


@pytest.mark.anyio
async def test_gateway_missing_api_key(db_session):
    settings = get_settings()
    settings.deepseek_api_key = ""  # Clear key

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY is not configured"):
        await DeepSeekGateway.generate_completion(
            db=db_session, agent_name="NewsAgent", model="deepseek-chat", messages=[{"role": "user", "content": "test"}]
        )


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_gateway_successful_chat_call(mock_post, db_session):
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"
    settings.deepseek_daily_budget_usd = Decimal("1.00")

    # Mock HTTP response data
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Silver spot price is bullish."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 250, "total_tokens": 400},
    }
    mock_post.return_return_value = mock_response
    mock_post.return_value = mock_response

    response = await DeepSeekGateway.generate_completion(
        db=db_session,
        agent_name="NewsAgent",
        model="deepseek-chat",
        messages=[{"role": "user", "content": "What is the silver trend?"}],
    )

    assert response["content"] == "Silver spot price is bullish."
    assert response["prompt_tokens"] == 150
    assert response["completion_tokens"] == 250
    assert response["cost_usd"] == calculate_llm_cost("deepseek-chat", 150, 250)

    # Check that a trace was logged to SQLite database
    traces = db_session.query(LLMCallTrace).all()
    assert len(traces) == 1
    assert traces[0].agent_name == "NewsAgent"
    assert traces[0].model_name == "deepseek-chat"
    assert traces[0].status == "SUCCESS"
    assert traces[0].prompt_tokens == 150
    assert traces[0].total_cost_usd == response["cost_usd"]


@pytest.mark.anyio
@patch("httpx.AsyncClient.post")
async def test_gateway_reasoner_thinking(mock_post, db_session):
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "id": "chatcmpl-mock-reasoner",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Execute risk reduction.",
                    "reasoning_content": "Calculating volatility... volatility is 15%... daily loss limit is close... let's reduce risk.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 500, "completion_tokens": 800, "total_tokens": 1300},
    }
    mock_post.return_value = mock_response

    response = await DeepSeekGateway.generate_completion(
        db=db_session,
        agent_name="RiskAgent",
        model="deepseek-reasoner",
        messages=[{"role": "user", "content": "Evaluate risk."}],
    )

    assert response["content"] == "Execute risk reduction."
    assert (
        response["reasoning_content"]
        == "Calculating volatility... volatility is 15%... daily loss limit is close... let's reduce risk."
    )
    assert response["prompt_tokens"] == 500
    assert response["completion_tokens"] == 800
    assert response["cost_usd"] == calculate_llm_cost("deepseek-reasoner", 500, 800)

    # Confirm DB trace logging
    trace = db_session.query(LLMCallTrace).filter_by(agent_name="RiskAgent").first()
    assert trace is not None
    assert trace.model_name == "deepseek-reasoner"
    assert trace.status == "SUCCESS"


from pydantic import BaseModel


class MockResponseModel(BaseModel):
    decision: str
    confidence: Decimal


@pytest.mark.anyio
@patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock)
async def test_gateway_structured_completion(mock_create, db_session):
    settings = get_settings()
    settings.deepseek_api_key = "sk-mock-key"

    # Create a mock ChatCompletion response representing the raw LLM output
    mock_message = AsyncMock()
    mock_message.content = '{"decision": "BUY", "confidence": "0.9500"}'
    mock_message.refusal = None

    mock_choice = AsyncMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_usage = AsyncMock()
    mock_usage.prompt_tokens = 120
    mock_usage.completion_tokens = 220

    mock_response = AsyncMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    # mock_create needs to return the AsyncMock of ChatCompletion
    mock_create.return_value = mock_response

    response = await DeepSeekGateway.generate_structured_completion(
        db=db_session,
        agent_name="RiskAgent",
        model="deepseek-chat",
        messages=[{"role": "user", "content": "Return structured decision"}],
        response_model=MockResponseModel,
    )

    assert response.decision == "BUY"
    assert response.confidence == Decimal("0.9500")

    # Confirm DB trace logging was captured
    trace = (
        db_session.query(LLMCallTrace)
        .filter_by(agent_name="RiskAgent")
        .filter(LLMCallTrace.prompt_raw.like("%structured%"))
        .first()
    )
    assert trace is not None
    assert trace.model_name == "deepseek-chat"
    assert trace.status == "SUCCESS"
    assert trace.prompt_tokens == 120
    assert trace.completion_tokens == 220
