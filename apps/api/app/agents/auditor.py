import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import AgentMemoryEvent, LLMCallTrace

logger = logging.getLogger("silverpilot.agents.auditor")


async def run_system_audit(db: Session) -> AgentMemoryEvent:
    """
    Analyzes recent agent activities, detects logged agent disagreements,
    queries LLM call traces to compute recent budget usage and latency metrics,
    calls DeepSeek (deepseek-v4-pro) to perform a comprehensive System Audit,
    saves the structured results into AgentMemoryEvent, and returns the record.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # 1. Fetch recent agent disagreements from AgentMemoryEvent
    stmt_disagreements = (
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.event_type == "agent_disagreement")
        .where(AgentMemoryEvent.created_at >= twenty_four_hours_ago)
        .order_by(desc(AgentMemoryEvent.created_at))
        .limit(10)
    )
    disagreements = db.execute(stmt_disagreements).scalars().all()
    disagreements_list = [d.value_json for d in disagreements]

    # 2. Query LLM call traces to get budget consumption details
    stmt_traces = select(LLMCallTrace).where(LLMCallTrace.created_at >= twenty_four_hours_ago)
    traces = db.execute(stmt_traces).scalars().all()

    # Aggregate token costs and latencies
    total_cost = 0.0
    cost_by_model = {}
    total_calls = len(traces)
    total_latency = 0

    for trace in traces:
        cost = float(trace.total_cost_usd)
        total_cost += cost
        model_name = trace.model_name
        cost_by_model[model_name] = cost_by_model.get(model_name, 0.0) + cost
        total_latency += trace.latency_ms

    avg_latency = float(total_latency) / total_calls if total_calls > 0 else 0.0

    budget_status = {
        "total_cost_usd_24h": total_cost,
        "total_calls_24h": total_calls,
        "average_latency_ms": avg_latency,
        "cost_by_model": cost_by_model,
        "daily_budget_limit": 1.00,  # $1.00 USD standard limit
    }

    # 3. Fetch latest memory events for context from other core agents
    core_events_data = {}
    for agent in ["news-agent", "risk-agent", "market-research-agent", "ml-analyst-agent", "source-reliability-agent"]:
        stmt_mem = (
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.agent_name == agent)
            .order_by(desc(AgentMemoryEvent.created_at))
            .limit(1)
        )
        mem = db.execute(stmt_mem).scalar_one_or_none()
        if mem and mem.value_json:
            core_events_data[agent] = mem.value_json

    # 4. Call LLM to run system audit
    model = "deepseek-v4-pro"
    system_prompt = (
        "You are an expert lead systems auditor and technical operations inspector for the SilverPilot multi-agent platform.\n"
        "Your task is to analyze system events, conflicts/disagreements between trading agents, "
        "and total LLM API budget consumption metrics in the last 24 hours.\n"
        "Generate a professional, structured System Audit Report. Evaluate system stability, LLM cost efficiency, "
        "the presence of unresolved conflicts, and resource metrics.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "audit_markdown": string, a beautifully styled, technical audit report in markdown.\n\n'
        "Example response format:\n"
        "{\n"
        '  "audit_markdown": "# System Audit Report\\n- **LLM Budget**: 24h cost at $0.12 (limit $1.00). Ok.\\n- **Disagreements**: 0 conflicts detected."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"System Auditor Inputs:\n\n"
        f"Budget & Performance Metrics:\n{json.dumps(budget_status, indent=2)}\n\n"
        f"Agent Disagreements Recorded:\n{json.dumps(disagreements_list, indent=2)}\n\n"
        f"Latest Status of Core Agents:\n{json.dumps(core_events_data, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Auditor Agent LLM using model: {model}.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="auditor-agent",
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
        audit_markdown = str(data.get("audit_markdown", "No audit details provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Auditor LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        audit_markdown = (
            f"# System Audit Report (Error)\n\nFailed to parse LLM system audit details. Raw response:\n\n{raw_content}"
        )

    # 5. Save report to AgentMemoryEvent
    event = AgentMemoryEvent(
        agent_name="auditor-agent",
        event_type="system_audit",
        key="latest_analysis",
        value_json={
            "disagreements_found": disagreements_list,
            "budget_status": budget_status,
            "audit_markdown": audit_markdown,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"System Audit analysis completed. Event ID: {event.id}")
    return event
