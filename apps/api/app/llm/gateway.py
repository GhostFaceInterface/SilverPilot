import time
import httpx
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.core.config import get_settings
from app.llm.budget_guard import check_budget_limit

logger = logging.getLogger("silverpilot.llm_gateway")

# Official DeepSeek Pricing (USD per token)
# deepseek-chat (V3/V4): Input $0.14 / 1M tokens ($0.00000014), Output $0.28 / 1M tokens ($0.00000028)
# deepseek-reasoner (R1): Input $0.55 / 1M tokens ($0.00000055), Output $2.19 / 1M tokens ($0.00000219)
DEEPSEEK_PRICING = {
    "deepseek-chat": {"input": Decimal("0.00000014"), "output": Decimal("0.00000028")},
    "deepseek-reasoner": {"input": Decimal("0.00000055"), "output": Decimal("0.00000219")},
    "deepseek-v4-flash": {"input": Decimal("0.00000014"), "output": Decimal("0.00000028")},
    "deepseek-v4-pro": {"input": Decimal("0.000000435"), "output": Decimal("0.00000087")},
}


def calculate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """
    Calculates the exact cost of an LLM call based on token counts.
    Fallback pricing is applied if model is not recognized.
    """
    pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING["deepseek-v4-flash"])
    input_cost = Decimal(prompt_tokens) * pricing["input"]
    output_cost = Decimal(completion_tokens) * pricing["output"]
    return input_cost + output_cost


class DeepSeekGateway:
    """
    Gateway to official DeepSeek API, designed for secure and resource-friendly LLM calls.
    Supports deep reasoning choices ('choices[0].message.reasoning_content').
    """

    @staticmethod
    async def generate_completion(
        db: Session,
        agent_name: str,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_seconds: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Sends an asynchronous completion request directly to DeepSeek API.
        Enforces daily budget limits and records a call trace to database.
        """
        settings = get_settings()

        # 1. Ensure API key is configured
        if not settings.deepseek_api_key:
            err_msg = "DEEPSEEK_API_KEY is not configured in settings."
            logger.error(err_msg)
            raise ValueError(err_msg)

        # 2. Daily Budget limit check (Pre-flight guard)
        check_budget_limit(db, additional_cost=Decimal("0.0"))

        # Setup API details
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}

        # Build payload. deepseek-reasoner does not support temperature parameter in standard API
        payload = {
            "model": model,
            "messages": messages,
        }
        if model != "deepseek-reasoner":
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.perf_counter()
        status = "SUCCESS"
        error_msg = None
        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = Decimal("0.000000")
        response_content = ""
        reasoning_content = ""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=timeout_seconds)

                # Check for standard HTTP errors
                response.raise_for_status()
                response_data = response.json()

            # Parse token usage
            usage = response_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cost_usd = calculate_llm_cost(model, prompt_tokens, completion_tokens)

            # Post-call budget limit validation to ensure we catch over-budget charges immediately
            check_budget_limit(db, additional_cost=cost_usd)

            # Extract content and reasoning block
            choice = response_data["choices"][0]
            message = choice["message"]
            response_content = message.get("content") or ""
            reasoning_content = message.get("reasoning_content") or ""

        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            logger.exception(f"DeepSeek API call failed: {error_msg}")

        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)

            # Log trace into database asynchronously/safely
            try:
                from app.models import LLMCallTrace

                trace = LLMCallTrace(
                    agent_name=agent_name,
                    model_name=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    status=status,
                    prompt_raw=str(messages),
                    response_raw=response_content if status == "SUCCESS" else None,
                    error_message=error_msg,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(trace)
                db.commit()
            except Exception as db_err:
                logger.error(f"Failed to log LLM call trace to database: {db_err}")

        if status == "FAILED":
            raise RuntimeError(f"DeepSeek LLM execution failed: {error_msg}")

        return {
            "content": response_content,
            "reasoning_content": reasoning_content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
        }

    @staticmethod
    async def generate_structured_completion(
        db: Session,
        agent_name: str,
        model: str,
        messages: List[Dict[str, str]],
        response_model: Any,
        max_retries: int = 2,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_seconds: float = 60.0,
    ) -> Any:
        """
        Sends an asynchronous completion request directly to DeepSeek API,
        using the Instructor library to validate the JSON response against a Pydantic schema.
        Supports automatic self-healing prompt retries (up to max_retries times).
        Logs a call trace to the database for each execution.
        """
        import instructor
        from openai import AsyncOpenAI

        settings = get_settings()

        if not settings.deepseek_api_key:
            err_msg = "DEEPSEEK_API_KEY is not configured in settings."
            logger.error(err_msg)
            raise ValueError(err_msg)

        # Daily Budget limit check (Pre-flight guard)
        check_budget_limit(db, additional_cost=Decimal("0.0"))

        # Configure instructor wrapped async client
        # DeepSeek is OpenAI-compatible
        openai_client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)

        # We use instructor's native async patcher
        instructor_client = instructor.from_openai(openai_client, mode=instructor.Mode.JSON)

        start_time = time.perf_counter()
        status = "SUCCESS"
        error_msg = None
        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = Decimal("0.000000")
        response_content = ""

        try:
            # Send completion request using instructor wrapper
            # Max_retries specifies self-healing cycles
            kwargs = {
                "model": model,
                "messages": messages,
                "response_model": response_model,
                "max_retries": max_retries,
                "timeout": timeout_seconds,
            }
            if model != "deepseek-reasoner":
                kwargs["temperature"] = temperature
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            # The structured object returned by instructor
            structured_result = await instructor_client.chat.completions.create(**kwargs)

            try:
                raw_resp = getattr(structured_result, "_raw_response", None)
                if raw_resp:
                    usage = getattr(raw_resp, "usage", None)
                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", 0)
                        completion_tokens = getattr(usage, "completion_tokens", 0)
            except Exception as usage_err:
                logger.debug(f"Could not retrieve token usage from instructor result: {usage_err}")

            # Fallback estimation if token usage is 0
            if prompt_tokens == 0:
                prompt_tokens = len(str(messages)) // 4
                completion_tokens = len(str(structured_result)) // 4

            cost_usd = calculate_llm_cost(model, prompt_tokens, completion_tokens)

            # Post-call budget validation to ensure we catch over-budget charges immediately
            check_budget_limit(db, additional_cost=cost_usd)

            response_content = (
                structured_result.model_dump_json()
                if hasattr(structured_result, "model_dump_json")
                else str(structured_result)
            )
            return structured_result

        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            logger.exception(f"Instructor DeepSeek structured call failed: {error_msg}")
            raise RuntimeError(f"DeepSeek LLM execution failed: {error_msg}")

        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)

            # Log trace into database
            try:
                from app.models import LLMCallTrace

                trace = LLMCallTrace(
                    agent_name=agent_name,
                    model_name=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    status=status,
                    prompt_raw=str(messages),
                    response_raw=response_content if status == "SUCCESS" else None,
                    error_message=error_msg,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(trace)
                db.commit()
            except Exception as db_err:
                logger.error(f"Failed to log LLM call trace in generate_structured_completion: {db_err}")


def trace_llm(agent_name: str, model_name: str):
    """
    Decorator to trace arbitrary LLM calls. Measures latency and logs success/failure to db.
    Expects the decorated function's first argument or a named keyword argument 'db' to be an active Session,
    and returns a dict or tuple containing prompt_tokens and completion_tokens.
    """
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            db = kwargs.get("db")
            if not db:
                for arg in args:
                    if isinstance(arg, Session):
                        db = arg
                        break

            if not db:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            status = "SUCCESS"
            error_msg = None
            prompt_tokens = 0
            completion_tokens = 0
            cost_usd = Decimal("0.0")
            response_content = None
            prompt_raw = f"decorator[{func.__name__}]"

            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict):
                    prompt_tokens = result.get("prompt_tokens", 0)
                    completion_tokens = result.get("completion_tokens", 0)
                    response_content = result.get("content", str(result))
                    cost_usd = result.get("cost_usd", calculate_llm_cost(model_name, prompt_tokens, completion_tokens))
                else:
                    response_content = str(result)
                    cost_usd = calculate_llm_cost(model_name, 0, 0)
                return result
            except Exception as e:
                status = "FAILED"
                error_msg = str(e)
                raise e
            finally:
                end_time = time.perf_counter()
                latency_ms = int((end_time - start_time) * 1000)
                try:
                    from app.models import LLMCallTrace
                    from datetime import datetime, timezone

                    trace = LLMCallTrace(
                        agent_name=agent_name,
                        model_name=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_cost_usd=Decimal(str(cost_usd)),
                        latency_ms=latency_ms,
                        status=status,
                        prompt_raw=prompt_raw,
                        response_raw=response_content,
                        error_message=error_msg,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(trace)
                    db.commit()
                except Exception as db_err:
                    logger.error(f"trace_llm decorator failed to save trace: {db_err}")

        return async_wrapper

    return decorator
