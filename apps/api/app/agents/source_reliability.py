import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import AgentMemoryEvent
from app.collectors.service import collector_validation_gate

logger = logging.getLogger("silverpilot.agents.source_reliability")


async def run_source_reliability_analysis(db: Session) -> AgentMemoryEvent:
    """
    Retrieves collector run statistics, health states, and quality summaries.
    Calls DeepSeek (deepseek-v4-flash) to evaluate source reliability, generate trust scores,
    and output a comprehensive system diagnostic and trust report in AgentMemoryEvent.
    """
    now = datetime.now(timezone.utc)

    # 1. Fetch collector validation gate details
    try:
        validation_data = collector_validation_gate(
            db, window_hours=24, expected_interval_minutes=15, stale_after_minutes=60
        )
    except Exception as e:
        logger.warning(f"Failed to fetch collector validation data: {e}. Using fallback.")
        validation_data = {
            "status": "empty",
            "health_status": "empty",
            "quality_status": "empty",
            "source_reliability": [],
            "blocking_reasons": ["VALIDATION_GATE_ERROR"],
            "degraded_reasons": [str(e)],
        }

    # 2. Extract metrics & check empty DB gracefully
    reliability_list = validation_data.get("source_reliability", [])
    if not reliability_list and validation_data.get("status") == "empty":
        logger.info("No collector runs recorded in the database. Generating fallback event.")
        event = AgentMemoryEvent(
            agent_name="source-reliability-agent",
            event_type="source_reliability",
            key="latest_analysis",
            value_json={
                "status": "empty",
                "source_scores": [],
                "summary_markdown": "No data collection runs found in the database. Trust scoring cannot be computed.",
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 3. Call LLM to evaluate reliability
    model = "deepseek-v4-flash"
    system_prompt = (
        "You are an expert precious metals system data auditor and infrastructure analyst.\n"
        "Your task is to analyze recent data collector runs, failures, stale factors, and trust metrics.\n"
        "Assign a trust level, outline current data pipeline health, and offer advice on reliability risks.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "status": string, must be one of "healthy", "degraded", or "blocked" representing system state\n'
        '- "summary_markdown": string, a concise diagnostic audit report explaining trust levels and infrastructure issues.\n\n'
        "Example response format:\n"
        "{\n"
        '  "status": "healthy",\n'
        '  "summary_markdown": "**Data Quality & Trust Audit:**\\n- All primary collectors (Yahoo, TCMB) show 100% success rate.\\n- System is operating under healthy latency profiles."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"Source Reliability Inputs:\n\n"
        f"Overall Validation Status: {validation_data.get('status')}\n"
        f"Health Status: {validation_data.get('health_status')}\n"
        f"Quality Status: {validation_data.get('quality_status')}\n"
        f"Execution Critical Status: {validation_data.get('execution_critical_status')}\n"
        f"Blocking Reasons: {validation_data.get('blocking_reasons')}\n"
        f"Degraded Reasons: {validation_data.get('degraded_reasons')}\n\n"
        f"Individual Source Reliability Statistics:\n{json.dumps(reliability_list, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Source Reliability Agent LLM using model: {model}.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="source-reliability-agent",
        model=model,
        messages=messages,
        temperature=0.2,
    )

    raw_content = response.get("content", "").strip()

    # Clean markdown block wrapping if LLM included them
    if raw_content.startswith("```"):
        lines = raw_content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_content = "\n".join(lines).strip()

    if "```json" in raw_content:
        raw_content = raw_content.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_content:
        raw_content = raw_content.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(raw_content)
        status_result = str(data.get("status", "healthy")).lower()
        if status_result not in {"healthy", "degraded", "blocked"}:
            status_result = "healthy"
        summary_markdown = str(data.get("summary_markdown", "No summary provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Source Reliability LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        status_result = "degraded"
        summary_markdown = f"Failed to parse LLM source reliability analysis. Raw response:\n\n{raw_content}"

    # 4. Save analysis to AgentMemoryEvent
    event = AgentMemoryEvent(
        agent_name="source-reliability-agent",
        event_type="source_reliability",
        key="latest_analysis",
        value_json={
            "status": status_result,
            "source_scores": reliability_list,
            "summary_markdown": summary_markdown,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"Source Reliability analysis completed. Event ID: {event.id}")
    return event
