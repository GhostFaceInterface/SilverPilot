import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import TechnicalIndicator, RawEvent, AgentMemoryEvent, PriceSnapshot

logger = logging.getLogger("silverpilot.agents.market_research")


async def run_market_research_analysis(db: Session) -> AgentMemoryEvent:
    """
    Fetches the latest technical indicators, recent macroeconomic events, and price snapshots,
    calls the DeepSeek LLM (deepseek-v4-flash) to evaluate market trends and generate a sentiment score,
    saves the structured results into AgentMemoryEvent, and returns the event record.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # 1. Fetch latest technical indicator
    stmt_indicator = select(TechnicalIndicator).order_by(desc(TechnicalIndicator.bar_timestamp)).limit(1)
    technical_indicator = db.execute(stmt_indicator).scalar_one_or_none()

    # 2. Fetch latest price snapshot
    stmt_price = select(PriceSnapshot).order_by(desc(PriceSnapshot.observed_at)).limit(1)
    latest_price = db.execute(stmt_price).scalar_one_or_none()

    # 3. Fetch recent raw events (TCMB, FRED macroeconomic data)
    stmt_events = (
        select(RawEvent)
        .where(RawEvent.observed_at >= twenty_four_hours_ago)
        .order_by(desc(RawEvent.observed_at))
        .limit(10)
    )
    events = db.execute(stmt_events).scalars().all()

    # Fallback if no recent events, get the latest 5 events as fallback
    if not events:
        stmt_events_fallback = select(RawEvent).order_by(desc(RawEvent.observed_at)).limit(5)
        events = db.execute(stmt_events_fallback).scalars().all()

    # 4. Handle empty database gracefully
    if not technical_indicator and not latest_price and not events:
        logger.info("No recent market research data found in database. Generating fallback event.")
        event = AgentMemoryEvent(
            agent_name="market-research-agent",
            event_type="market_trend",
            key="latest_analysis",
            value_json={
                "sentiment": "NEUTRAL",
                "confidence": 0.0,
                "summary_markdown": "No active market data (prices, indicators, or events) found in the database.",
                "indicators_analyzed": {},
                "macro_data": {},
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 5. Format inputs for the prompt
    indicators_dict = {}
    if technical_indicator:
        indicators_dict = {
            "rsi_14": float(technical_indicator.rsi_14) if technical_indicator.rsi_14 else None,
            "macd_line": float(technical_indicator.macd_line) if technical_indicator.macd_line else None,
            "macd_signal": float(technical_indicator.macd_signal) if technical_indicator.macd_signal else None,
            "macd_histogram": float(technical_indicator.macd_histogram) if technical_indicator.macd_histogram else None,
            "sma_20": float(technical_indicator.sma_20) if technical_indicator.sma_20 else None,
            "sma_50": float(technical_indicator.sma_50) if technical_indicator.sma_50 else None,
            "sma_200": float(technical_indicator.sma_200) if technical_indicator.sma_200 else None,
            "xau_xag_ratio": float(technical_indicator.xau_xag_ratio) if technical_indicator.xau_xag_ratio else None,
            "bar_timestamp": technical_indicator.bar_timestamp.isoformat() if technical_indicator.bar_timestamp else None,
        }

    price_dict = {}
    if latest_price:
        price_dict = {
            "mid_price": float(latest_price.mid_price),
            "buy_price": float(latest_price.buy_price),
            "sell_price": float(latest_price.sell_price),
            "spread_percent": float(latest_price.spread_percent) if latest_price.spread_percent else 0.0,
            "observed_at": latest_price.observed_at.isoformat(),
        }

    events_list = []
    for e in events:
        events_list.append({
            "source": e.source,
            "event_type": e.event_type,
            "observed_at": e.observed_at.isoformat(),
            "payload": e.payload_json,
        })

    # 6. Call LLM
    model = "deepseek-v4-flash"
    system_prompt = (
        "You are an expert precious metals market research analyst specializing in Silver (XAG) macroeconomic trends.\n"
        "Analyze the provided technical indicators, latest price snapshot, and recent macroeconomic events (such as FRED rates or TCMB data) to evaluate the prevailing market trends.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "sentiment": string, must be one of "BULLISH", "BEARISH", or "NEUTRAL"\n'
        '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
        '- "summary_markdown": string, a concise markdown report detailing your market research and reasoning.\n\n'
        "Example response format:\n"
        "{\n"
        '  "sentiment": "BULLISH",\n'
        '  "confidence": 0.82,\n'
        '  "summary_markdown": "**Market Research Summary:**\\n- Indicators show oversold conditions on technical frames.\\n- Macro indicators suggest holding momentum."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"Market Research Inputs:\n\n"
        f"Technical Indicators:\n{json.dumps(indicators_dict, indent=2)}\n\n"
        f"Latest Price Snapshot:\n{json.dumps(price_dict, indent=2)}\n\n"
        f"Recent Macroeconomic/Collector Events:\n{json.dumps(events_list, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Market Research Agent LLM using model: {model}.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="market-research-agent",
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
        sentiment = str(data.get("sentiment", "NEUTRAL")).upper()
        if sentiment not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            sentiment = "NEUTRAL"
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        summary_markdown = str(data.get("summary_markdown", "No summary provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Market Research LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        sentiment = "NEUTRAL"
        confidence = 0.5
        summary_markdown = f"Failed to parse LLM market research analysis. Raw response:\n\n{raw_content}"

    # 7. Save to AgentMemoryEvent
    event = AgentMemoryEvent(
        agent_name="market-research-agent",
        event_type="market_trend",
        key="latest_analysis",
        value_json={
            "sentiment": sentiment,
            "confidence": confidence,
            "summary_markdown": summary_markdown,
            "indicators_analyzed": indicators_dict,
            "macro_data": {"events_count": len(events_list)},
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"Market Research analysis completed. Event ID: {event.id}")
    return event
