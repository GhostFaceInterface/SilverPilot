import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.gateway import DeepSeekGateway
from app.models.entities import Signal, TechnicalIndicator, Portfolio, PortfolioSnapshot, AgentMemoryEvent

logger = logging.getLogger("silverpilot.agents.risk")


async def run_signal_critique(db: Session, signal_id: int | None = None) -> AgentMemoryEvent:
    """
    Retrieves the target or latest Signal, corresponding TechnicalIndicator and PortfolioSnapshot,
    calls DeepSeek to perform a risk audit (critique) of the BUY/SELL decision,
    saves the results as an AgentMemoryEvent, and returns it.
    """
    now = datetime.now(timezone.utc)

    # 1. Retrieve the signal
    if signal_id is not None:
        stmt = select(Signal).where(Signal.id == signal_id)
        signal = db.execute(stmt).scalar_one_or_none()
        if signal is None:
            logger.error(f"Signal with ID {signal_id} was not found.")
            raise ValueError(f"Signal with ID {signal_id} not found.")
    else:
        stmt = select(Signal).order_by(desc(Signal.created_at)).limit(1)
        signal = db.execute(stmt).scalar_one_or_none()

    # 2. Handle empty database gracefully
    if signal is None:
        logger.info("No signals exist in the database. Gracefully bypassing LLM calling.")
        event = AgentMemoryEvent(
            agent_name="risk-agent",
            event_type="signal_critique",
            key="critique_signal_none",
            value_json={
                "decision": "APPROVED",
                "confidence": 1.0,
                "critique_markdown": "No signals exist in the database. Gracefully bypassed LLM calling.",
                "signal_id": None,
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 3. Retrieve latest/associated TechnicalIndicator
    technical_indicator = None
    if signal.indicator_id is not None:
        technical_indicator = db.execute(
            select(TechnicalIndicator).where(TechnicalIndicator.id == signal.indicator_id)
        ).scalar_one_or_none()

    if technical_indicator is None:
        stmt_indicator = select(TechnicalIndicator).order_by(desc(TechnicalIndicator.bar_timestamp)).limit(1)
        technical_indicator = db.execute(stmt_indicator).scalar_one_or_none()

    # 4. Retrieve current PortfolioSnapshot
    portfolio = db.execute(select(Portfolio).order_by(desc(Portfolio.created_at)).limit(1)).scalar_one_or_none()
    portfolio_snapshot = None
    if portfolio is not None:
        stmt_snapshot = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.portfolio_id == portfolio.id)
            .order_by(desc(PortfolioSnapshot.observed_at))
            .limit(1)
        )
        portfolio_snapshot = db.execute(stmt_snapshot).scalar_one_or_none()

    if portfolio_snapshot is not None:
        portfolio_data = {
            "cash_balance": float(portfolio_snapshot.cash_balance),
            "asset_quantity": float(portfolio_snapshot.asset_quantity),
            "portfolio_value": float(portfolio_snapshot.portfolio_value),
            "realized_pnl": float(portfolio_snapshot.realized_pnl),
            "unrealized_pnl": float(portfolio_snapshot.unrealized_pnl),
        }
    else:
        portfolio_data = {
            "cash_balance": 10000.0,
            "asset_quantity": 0.0,
            "portfolio_value": 10000.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        }

    # 5. Format indicators
    if technical_indicator is not None:
        formatted_indicators = (
            f"- RSI (14): {technical_indicator.rsi_14}\n"
            f"- MACD Line: {technical_indicator.macd_line}\n"
            f"- MACD Signal: {technical_indicator.macd_signal}\n"
            f"- MACD Histogram: {technical_indicator.macd_histogram}\n"
            f"- BB Upper: {technical_indicator.bb_upper_20_2}\n"
            f"- BB Middle: {technical_indicator.bb_middle_20_2}\n"
            f"- BB Lower: {technical_indicator.bb_lower_20_2}\n"
            f"- SMA 20: {technical_indicator.sma_20}\n"
            f"- SMA 50: {technical_indicator.sma_50}\n"
            f"- SMA 200: {technical_indicator.sma_200}\n"
            f"- ATR 14: {technical_indicator.atr_14}\n"
            f"- XAU/XAG Ratio: {technical_indicator.xau_xag_ratio}\n"
            f"- Bar Timestamp: {technical_indicator.bar_timestamp.isoformat() if technical_indicator.bar_timestamp else 'N/A'}"
        )
    else:
        formatted_indicators = "No technical indicators available."

    # 6. Call DeepSeek via gateway
    settings = get_settings()
    model = settings.agent_risk_model

    system_prompt = (
        "You are an expert precious metals risk analyst and automated audit system.\n"
        "Your task is to analyze and critique a proposed BUY/SELL trading signal based on "
        "the latest technical indicators and current portfolio status.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "decision": string, must be one of "APPROVED", "CAUTION", or "REJECTED"\n'
        '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
        '- "critique_markdown": string, a concise markdown summary explaining your reasoning, risks, and audit notes.\n\n'
        "Example response format:\n"
        "{\n"
        '  "decision": "CAUTION",\n'
        '  "confidence": 0.78,\n'
        '  "critique_markdown": "**Risk Audit Report:**\\n- RSI at 75 indicates overbought condition.\\n- Volatility is high. Suggest caution."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"Proposed Signal:\n"
        f"- Action: {signal.action}\n"
        f"- Price: {signal.price_usd_oz} USD/oz\n"
        f"- Reason: {signal.reason_code}\n"
        f"- Details: {signal.details_json}\n\n"
        f"Technical Indicators:\n"
        f"{formatted_indicators}\n\n"
        f"Current Portfolio Snapshot:\n"
        f"- Cash Balance: {portfolio_data['cash_balance']} USD\n"
        f"- Asset Quantity: {portfolio_data['asset_quantity']} oz\n"
        f"- Total Portfolio Value: {portfolio_data['portfolio_value']} USD\n"
        f"- Realized PnL: {portfolio_data['realized_pnl']} USD\n"
        f"- Unrealized PnL: {portfolio_data['unrealized_pnl']} USD\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Risk Agent LLM using model: {model} to audit signal ID {signal.id}.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="risk-agent",
        model=model,
        messages=messages,
        temperature=0.2,
    )

    raw_content = response.get("content", "").strip()

    # Clean markdown formatting wraps if any
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
        decision = str(data.get("decision", "APPROVED")).upper()
        if decision not in {"APPROVED", "CAUTION", "REJECTED"}:
            decision = "APPROVED"
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        critique_markdown = str(data.get("critique_markdown", "No critique provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Risk Agent LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        decision = "APPROVED"
        confidence = 0.5
        critique_markdown = f"Failed to parse LLM risk audit analysis. Raw response:\n\n{raw_content}"

    # Save critique to database
    event = AgentMemoryEvent(
        agent_name="risk-agent",
        event_type="signal_critique",
        key=f"critique_signal_{signal.id}",
        value_json={
            "decision": decision,
            "confidence": confidence,
            "critique_markdown": critique_markdown,
            "signal_id": signal.id,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"Risk signal critique completed and saved successfully. Event ID: {event.id}")
    return event
