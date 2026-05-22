import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import PaperTrade, RiskDecision, AgentMemoryEvent

logger = logging.getLogger("silverpilot.agents.postmortem")


async def run_postmortem_analysis(db: Session) -> AgentMemoryEvent:
    """
    Fetches recently blocked paper trades and their corresponding risk decisions,
    calls DeepSeek (deepseek-v4-pro) to perform a detailed postmortem safety and risk analysis,
    saves the results as an AgentMemoryEvent, and returns the event record.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # 1. Fetch blocked trades in the last 24 hours
    stmt_blocked = (
        select(PaperTrade)
        .where(PaperTrade.action == "blocked")
        .where(PaperTrade.created_at >= twenty_four_hours_ago)
        .order_by(desc(PaperTrade.created_at))
    )
    blocked_trades = db.execute(stmt_blocked).scalars().all()

    # 2. Fallback to latest 5 blocked trades if none found in 24 hours
    if not blocked_trades:
        stmt_fallback = (
            select(PaperTrade).where(PaperTrade.action == "blocked").order_by(desc(PaperTrade.created_at)).limit(5)
        )
        blocked_trades = db.execute(stmt_fallback).scalars().all()

    # 3. Graceful fallback if no blocked trades exist
    if not blocked_trades:
        logger.info("No blocked paper trades exist in the database. Generating default clean postmortem event.")
        event = AgentMemoryEvent(
            agent_name="postmortem-agent",
            event_type="postmortem_analysis",
            key="latest_analysis",
            value_json={
                "blocked_trades_count": 0,
                "details_markdown": "# Postmortem Analysis Report (Clean)\n\nNo blocked paper trades or active risk violations were recorded in the analyzed window. System operations are running within regular parameters.",
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 4. Format blocked trades and risk decisions
    trades_data = []
    for trade in blocked_trades:
        decision_code = "UNKNOWN"
        risk_level = "UNKNOWN"
        details_json = {}

        # Load associated RiskDecision
        if trade.risk_decision_id is not None:
            decision = db.execute(
                select(RiskDecision).where(RiskDecision.id == trade.risk_decision_id)
            ).scalar_one_or_none()
            if decision is not None:
                decision_code = decision.reason_code
                risk_level = decision.risk_level
                details_json = decision.details_json

        trades_data.append(
            {
                "trade_id": trade.id,
                "portfolio_id": trade.portfolio_id,
                "quantity": float(trade.quantity),
                "price": float(trade.price),
                "gross_amount": float(trade.gross_amount),
                "net_amount": float(trade.net_amount),
                "created_at": trade.created_at.isoformat(),
                "block_reason_code": decision_code,
                "risk_level": risk_level,
                "block_details": details_json,
            }
        )

    # 5. Call LLM to run postmortem critique
    model = "deepseek-v4-pro"
    system_prompt = (
        "You are an expert precious metals financial risk controller and postmortem engineer.\n"
        "Your task is to analyze recently blocked paper-trade records and the corresponding "
        "risk decisions that triggered the blocks (such as SPREAD_TOO_HIGH, VOLATILITY_TOO_HIGH, daily loss limits, etc.).\n"
        "Generate a professional, detailed postmortem report that details the safety impact of each block, "
        "assesses whether the risk mechanism functioned properly, and provides strategic recommendations to improve "
        "the signal execution layers.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "details_markdown": string, a beautifully styled, technical postmortem audit report in markdown.\n\n'
        "Example response format:\n"
        "{\n"
        '  "details_markdown": "# Trade Postmortem Analysis\\n- **Trade #4**: Blocked for SPREAD_TOO_HIGH.\\n- **Safety Impact**: Prevented buying at 6% premium. High severity."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"Postmortem Inputs (Blocked Trades):\n\n"
        f"Blocked Trades Count: {len(trades_data)}\n"
        f"Blocked Trades List:\n{json.dumps(trades_data, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Postmortem Agent LLM using model: {model} with {len(blocked_trades)} blocked trades.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="postmortem-agent",
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
        details_markdown = str(data.get("details_markdown", "No details provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Postmortem LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        details_markdown = (
            f"# Postmortem Analysis (Error)\n\nFailed to parse LLM postmortem report. Raw response:\n\n{raw_content}"
        )

    # 6. Save report to AgentMemoryEvent
    event = AgentMemoryEvent(
        agent_name="postmortem-agent",
        event_type="postmortem_analysis",
        key="latest_analysis",
        value_json={
            "blocked_trades_count": len(blocked_trades),
            "details_markdown": details_markdown,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"Postmortem analysis completed. Event ID: {event.id}")
    return event
