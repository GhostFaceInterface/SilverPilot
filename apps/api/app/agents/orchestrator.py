import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import AgentMemoryEvent
from app.agents.hermes import run_hermes_sentiment_analysis
from app.agents.risk import run_signal_critique
from app.agents.market_research import run_market_research_analysis
from app.agents.ml_analyst import run_ml_inference_critique
from app.agents.source_reliability import run_source_reliability_analysis
from app.agents.postmortem import run_postmortem_analysis
from app.agents.auditor import run_system_audit

logger = logging.getLogger("silverpilot.agents.orchestrator")


async def run_multi_agent_analysis(db: Session, signal_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Orchestrates the sequential execution of all SilverPilot agents.
    Detects disagreements/contradictions between agent outcomes,
    logs any conflicts as an 'agent_disagreement' Event,
    triggers DeepSeek (deepseek-v4-pro) to act as Supreme Arbiter to resolve them,
    and returns the structured analyses and resolution summaries.
    """
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")

    results = {}
    errors = {}

    # 1. Run Core and Auxiliary Agents Sequentially

    # News Agent (Hermes)
    try:
        results["news"] = await run_hermes_sentiment_analysis(db)
    except Exception as e:
        logger.exception("Hermes agent execution failed")
        errors["news"] = str(e)

    # Risk Agent
    try:
        results["risk"] = await run_signal_critique(db, signal_id=signal_id)
    except Exception as e:
        logger.exception("Risk agent execution failed")
        errors["risk"] = str(e)

    # Market Research Agent
    try:
        results["market_research"] = await run_market_research_analysis(db)
    except Exception as e:
        logger.exception("Market Research agent execution failed")
        errors["market_research"] = str(e)

    # ML Analyst Agent
    try:
        results["ml_analyst"] = await run_ml_inference_critique(db)
    except Exception as e:
        logger.exception("ML Analyst agent execution failed")
        errors["ml_analyst"] = str(e)

    # Source Reliability Agent
    try:
        results["source_reliability"] = await run_source_reliability_analysis(db)
    except Exception as e:
        logger.exception("Source Reliability agent execution failed")
        errors["source_reliability"] = str(e)

    # Postmortem Agent
    try:
        results["postmortem"] = await run_postmortem_analysis(db)
    except Exception as e:
        logger.exception("Postmortem agent execution failed")
        errors["postmortem"] = str(e)

    # Auditor Agent
    try:
        results["auditor"] = await run_system_audit(db)
    except Exception as e:
        logger.exception("Auditor agent execution failed")
        errors["auditor"] = str(e)

    # 2. Extract Agent Stances for Disagreement Detection
    news_sentiment = "NEUTRAL"
    risk_decision = "APPROVED"
    market_sentiment = "NEUTRAL"
    ml_recommendation = "NEUTRAL"

    if "news" in results:
        news_sentiment = str(results["news"].value_json.get("sentiment", "NEUTRAL")).upper()
    if "risk" in results:
        risk_decision = str(results["risk"].value_json.get("decision", "APPROVED")).upper()
    if "market_research" in results:
        market_sentiment = str(results["market_research"].value_json.get("sentiment", "NEUTRAL")).upper()
    if "ml_analyst" in results:
        ml_recommendation = str(results["ml_analyst"].value_json.get("recommendation", "NEUTRAL")).upper()

    # 3. Detect Disagreements / Contradictions
    disagreements = []

    # Conflict A: News Sentiment vs Market Research Sentiment
    if (news_sentiment == "BULLISH" and market_sentiment == "BEARISH") or (
        news_sentiment == "BEARISH" and market_sentiment == "BULLISH"
    ):
        disagreements.append(
            {
                "type": "SENTIMENT_CONTRADICTION",
                "description": f"Sentiment contradiction: News is {news_sentiment} while Market Research is {market_sentiment}.",
            }
        )

    # Conflict B: ML Veto with positive sentiments
    if ml_recommendation == "VETO" and (news_sentiment == "BULLISH" or market_sentiment == "BULLISH"):
        disagreements.append(
            {
                "type": "ML_VETO_WITH_BULLISH_SENTIMENT",
                "description": f"ML Analyst recommended VETO despite bullish signals (News: {news_sentiment}, Market Research: {market_sentiment}).",
            }
        )

    # Conflict C: Risk Agent Rejection with positive sentiments
    if risk_decision == "REJECTED" and (news_sentiment == "BULLISH" or market_sentiment == "BULLISH"):
        disagreements.append(
            {
                "type": "RISK_REJECTION_WITH_BULLISH_SENTIMENT",
                "description": f"Risk Agent REJECTED trade signal despite bullish sentiments (News: {news_sentiment}, Market Research: {market_sentiment}).",
            }
        )

    # Conflict D: ML Analyst vs Risk Decision contradictions
    if ml_recommendation == "VETO" and risk_decision == "APPROVED":
        disagreements.append(
            {
                "type": "ML_VETO_VS_RISK_APPROVAL",
                "description": "ML Analyst recommended VETO but Risk Agent APPROVED the signal.",
            }
        )
    elif ml_recommendation == "APPROVE" and risk_decision == "REJECTED":
        disagreements.append(
            {
                "type": "ML_APPROVAL_VS_RISK_REJECTION",
                "description": "ML Analyst APPROVED the trade setup but Risk Agent REJECTED it.",
            }
        )

    disagreement_event = None
    resolution_event = None

    # 4. Resolve Disagreements via deepseek-v4-pro Supreme Arbiter
    if disagreements:
        logger.info(
            f"Disagreement detected: {len(disagreements)} conflicts found. Initiating Supreme Arbiter resolution."
        )

        # Log the disagreement event
        disagreement_event = AgentMemoryEvent(
            agent_name="orchestrator",
            event_type="agent_disagreement",
            key=f"disagreement_{timestamp_str}",
            value_json={
                "disagreements": disagreements,
                "stances": {
                    "news_sentiment": news_sentiment,
                    "risk_decision": risk_decision,
                    "market_sentiment": market_sentiment,
                    "ml_recommendation": ml_recommendation,
                },
                "recorded_at": now.isoformat(),
            },
        )
        db.add(disagreement_event)
        db.commit()
        db.refresh(disagreement_event)

        # Call Pro Supreme Arbiter
        model = "deepseek-v4-pro"

        # Compile agent summaries to feed resolution
        agent_summaries = {}
        for k, v in results.items():
            if hasattr(v, "value_json"):
                for field in ["summary_markdown", "critique_markdown", "analysis_markdown", "details_markdown"]:
                    if field in v.value_json:
                        agent_summaries[k] = v.value_json[field]
                        break

        system_prompt = (
            "You are the Supreme Financial Arbiter and Multi-Agent Orchestrator for SilverPilot.\n"
            "Your task is to analyze and resolve direct contradictions, disagreements, or conflicts "
            "between specialized trading agents (News, Risk, Market Research, and ML Analyst).\n"
            "Evaluate each agent's reasoning, assess the market evidence objectively, "
            "and output a unified, balanced resolution path.\n"
            "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
            '- "resolved_stance": string, must be one of "BULLISH", "BEARISH", "NEUTRAL", "VETO", or "ALLOW"\n'
            '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
            '- "resolution_markdown": string, a comprehensive technical breakdown of how you resolved the contradictions '
            "and your final recommendation path.\n\n"
            "Example response format:\n"
            "{\n"
            '  "resolved_stance": "VETO",\n'
            '  "confidence": 0.85,\n'
            '  "resolution_markdown": "**Arbiter Resolution:**\\n- ML Veto overrides news bullishness due to high volatility."\n'
            "}\n"
            "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
        )

        user_prompt = (
            f"Supreme Arbiter Resolution Inputs:\n\n"
            f"Detected Conflicts:\n{json.dumps(disagreements, indent=2)}\n\n"
            f"Agent Stances:\n"
            f"- News Sentiment: {news_sentiment}\n"
            f"- Risk Decision: {risk_decision}\n"
            f"- Market Research Sentiment: {market_sentiment}\n"
            f"- ML Analyst Recommendation: {ml_recommendation}\n\n"
            f"Agent Analyses and Reports Context:\n{json.dumps(agent_summaries, indent=2)}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Calling Supreme Arbiter LLM using model: {model} to resolve conflicts.")
        try:
            response = await DeepSeekGateway.generate_completion(
                db=db,
                agent_name="orchestrator-arbiter",
                model=model,
                messages=messages,
                temperature=0.2,
            )
            raw_content = response.get("content", "").strip()

            # Clean markdown code wrapper if present
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

            data = json.loads(raw_content)
            resolved_stance = str(data.get("resolved_stance", "NEUTRAL")).upper()
            if resolved_stance not in {"BULLISH", "BEARISH", "NEUTRAL", "VETO", "ALLOW"}:
                resolved_stance = "NEUTRAL"
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            resolution_markdown = str(data.get("resolution_markdown", "No details provided by arbiter."))

        except Exception as resolve_err:
            logger.warning(f"Supreme Arbiter execution or parse failed: {resolve_err}")
            resolved_stance = "NEUTRAL"
            confidence = 0.5
            resolution_markdown = (
                f"# Supreme Arbiter Resolution (Failed)\n\nConflict resolution failed to run or parse: {resolve_err}"
            )

        # Save resolution event
        resolution_event = AgentMemoryEvent(
            agent_name="orchestrator",
            event_type="disagreement_resolution",
            key=f"resolution_{timestamp_str}",
            value_json={
                "resolved_stance": resolved_stance,
                "confidence": confidence,
                "resolution_markdown": resolution_markdown,
                "disagreements": disagreements,
                "resolved_at": now.isoformat(),
            },
        )
        db.add(resolution_event)
        db.commit()
        db.refresh(resolution_event)

        logger.info(f"Supreme Arbiter conflict resolution completed. Event ID: {resolution_event.id}")

    return {
        "status": "success",
        "results": {k: v.id for k, v in results.items() if hasattr(v, "id")},
        "errors": errors,
        "disagreement": disagreement_event.id if disagreement_event else None,
        "resolution": resolution_event.id if resolution_event else None,
        "conflict_detected": len(disagreements) > 0,
    }


async def run_blended_consensus_resolution(
    db: Session,
    regime_info: dict,
    strategy_votes: dict,
    latest_snapshot,
    hermes_sentiment: dict | None = None,
) -> AgentMemoryEvent:
    """
    Blended Agentic Regime & Consensus Engine (Supreme Arbiter).
    Weights and resolves votes based on current Market Regime and Hermes news sentiment using deepseek-v4-pro.
    Saves the resolution into AgentMemoryEvent table under 'blended_consensus_resolution'.
    """
    from app.core.config import get_settings

    settings = get_settings()
    model = getattr(settings, "agent_risk_model", "deepseek-v4-pro") or "deepseek-v4-pro"

    system_prompt = (
        "You are the Supreme Financial Arbiter and Blended Consensus Engine for SilverPilot.\n"
        "Your task is to weight and consolidate multiple strategy signals (RSI, Bollinger Bands, SMA Cross) "
        "and Hermes news sentiment based on the detected Market Regime to determine a unified resolved stance.\n"
        "Guideline weighting rules:\n"
        "- In a SIDEWAYS regime, prioritize mean-reversion strategies like RSI and Bollinger Bands (e.g. 70-80% weight). "
        "Consider Hermes news sentiment with moderate weight (~20-30%).\n"
        "- In a TRENDING regime (TRENDING_UP / TRENDING_DOWN), prioritize trend-following strategies like SMA Cross (e.g. 70-80% weight). "
        "Consider Hermes news sentiment for confirmation (~10-20%).\n"
        "- If the Hermes news sentiment score is strongly bearish (score < -0.45), raise warnings/caution and bias towards a BEARISH or NEUTRAL stance.\n"
        "You must output a unified consolidated resolved stance: BULLISH, BEARISH, or NEUTRAL.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "resolved_stance": string, must be one of "BULLISH", "BEARISH", or "NEUTRAL"\n'
        '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
        '- "resolution_markdown": string, a highly-styled, comprehensive technical explanation of how you weighted the votes '
        "in this market regime and your final justification.\n\n"
        "Example response format:\n"
        "{\n"
        '  "resolved_stance": "BULLISH",\n'
        '  "confidence": 0.85,\n'
        '  "resolution_markdown": "Yatay piyasada (SIDEWAYS) RSI aşırı satım bölgesinde ve Bollinger alt bandına yakın. Trend zayıf olduğu için SMA sinyali göz ardı edildi."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    mid_p = float(latest_snapshot.mid_price) if latest_snapshot else 0.0
    user_prompt = (
        f"Consensus Resolution Inputs:\n\n"
        f"Market Snapshot Price: {mid_p:.4f} USD/oz\n"
        f"Detected Market Regime: {regime_info.get('regime', 'SIDEWAYS')} (ADX: {regime_info.get('adx', 0.0):.2f}, Bollinger Bandwidth: {regime_info.get('bb_bandwidth', 0.0):.4f})\n\n"
        f"Strategy Votes:\n"
        f"- RSI (14): {strategy_votes.get('rsi', {}).get('action')} ({strategy_votes.get('rsi', {}).get('reason')})\n"
        f"- Bollinger Bands: {strategy_votes.get('bollinger', {}).get('action')} ({strategy_votes.get('bollinger', {}).get('reason')})\n"
        f"- SMA Cross (20/50): {strategy_votes.get('sma_cross', {}).get('action')} ({strategy_votes.get('sma_cross', {}).get('reason')})\n"
    )

    if hermes_sentiment:
        score = hermes_sentiment.get("score", 0.0)
        sentiment = hermes_sentiment.get("sentiment", "NEUTRAL")
        articles_count = len(hermes_sentiment.get("articles") or [])
        user_prompt += (
            f"\nLatest Hermes News Sentiment:\n"
            f"- Sentiment Score: {score:.4f}\n"
            f"- Resolved Sentiment: {sentiment}\n"
            f"- Number of Articles Analyzed: {articles_count}\n"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Supreme Consensus Arbiter using model: {model}")
    try:
        response = await DeepSeekGateway.generate_completion(
            db=db,
            agent_name="blended-consensus-arbiter",
            model=model,
            messages=messages,
            temperature=0.1,
        )
        raw_content = response.get("content", "").strip()

        # Clean markdown code wrapper if present
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

        data = json.loads(raw_content)
        resolved_stance = str(data.get("resolved_stance", "NEUTRAL")).upper()
        if resolved_stance not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            resolved_stance = "NEUTRAL"
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        resolution_markdown = str(data.get("resolution_markdown", "No details provided by arbiter."))

    except Exception as e:
        logger.error(f"Supreme Arbiter call failed in blended consensus: {e}", exc_info=True)
        resolved_stance = "NEUTRAL"
        confidence = 0.5
        resolution_markdown = f"Consensus evaluation failed to run or parse: {e}"

    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    event = AgentMemoryEvent(
        agent_name="blended_consensus_orchestrator",
        event_type="blended_consensus_resolution",
        key=f"blended_{timestamp_str}",
        value_json={
            "resolved_stance": resolved_stance,
            "confidence": confidence,
            "resolution_markdown": resolution_markdown,
            "regime_info": regime_info,
            "strategy_votes": strategy_votes,
            "hermes_sentiment": hermes_sentiment,
            "recorded_at": now.isoformat(),
        },
    )
    db.add(event)
    db.flush()
    logger.info(f"Blended Consensus Resolution event created: {event.id}")
    return event
