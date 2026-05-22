import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.gateway import DeepSeekGateway
from app.models import Asset, AgentMemoryEvent
from app.ml.inference import get_active_model_metadata, predict_profitability, extract_live_features

logger = logging.getLogger("silverpilot.agents.ml_analyst")


async def run_ml_inference_critique(db: Session, asset_symbol: str = "XAG") -> AgentMemoryEvent:
    """
    Retrieves active ML model metadata, extracts live features, and generates profitability predictions.
    Calls DeepSeek (deepseek-v4-pro) to review the ML output, model metrics, feature significance,
    and generate a critique recommendation (APPROVE/VETO/NEUTRAL), saving the result in AgentMemoryEvent.
    """
    now = datetime.now(timezone.utc)

    # 1. Fetch asset
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        logger.warning(f"Asset with symbol {asset_symbol} not found in database. Using fallback.")
        asset_id = 1
    else:
        asset_id = asset.id

    # 2. Get active ML model metadata
    model_metadata = get_active_model_metadata()

    # 3. Extract live features
    df_feat = extract_live_features(db, asset_id)
    features_dict = {}
    if df_feat is not None and not df_feat.empty:
        features_dict = {col: float(df_feat[col].iloc[0]) for col in df_feat.columns}

    # 4. Predict profitability probability
    probability = predict_profitability(db, asset_id)

    # 5. Handle empty database or uninitialized ML environment gracefully
    if not features_dict and probability is None:
        logger.info("ML inference inputs are not fully available. Bypassing LLM calling.")
        event = AgentMemoryEvent(
            agent_name="ml-analyst-agent",
            event_type="ml_analysis",
            key="latest_analysis",
            value_json={
                "prediction_probability": None,
                "model_metadata": model_metadata,
                "recommendation": "NEUTRAL",
                "confidence": 1.0,
                "analysis_markdown": "ML inference environment or data is uninitialized. Critique bypassed.",
                "features": {},
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 6. Call deepseek-v4-pro to audit model quality & prediction
    model = "deepseek-v4-pro"
    system_prompt = (
        "You are a highly skilled quantitative machine learning auditor and risk analyst.\n"
        "Your task is to analyze machine learning model inferences, features, and predictability "
        "on the precious metals (Silver XAG) market.\n"
        "Critique the model's metrics, its features, and the predicted profitability probability.\n"
        "Provide a decision on whether you support the trade signal or want to initiate a veto.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "recommendation": string, must be one of "APPROVE", "VETO", or "NEUTRAL"\n'
        '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
        '- "analysis_markdown": string, a concise technical analysis explaining your findings, '
        "feature importances, and model decision critique.\n\n"
        "Example response format:\n"
        "{\n"
        '  "recommendation": "APPROVE",\n'
        '  "confidence": 0.88,\n'
        '  "analysis_markdown": "**ML Analysis Report:**\\n- High predictability (probability: 0.65).\\n- Input volatility and spread support the current signal."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = (
        f"Machine Learning Analyst Inputs:\n\n"
        f"Asset Symbol: {asset_symbol}\n"
        f"Model Metadata:\n{json.dumps(model_metadata, indent=2)}\n\n"
        f"Live Extracted Features:\n{json.dumps(features_dict, indent=2)}\n\n"
        f"Predicted Profitability Probability (3-day horizon): {probability if probability is not None else 'N/A'}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling ML Analyst Agent LLM using model: {model}.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="ml-analyst-agent",
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
        recommendation = str(data.get("recommendation", "NEUTRAL")).upper()
        if recommendation not in {"APPROVE", "VETO", "NEUTRAL"}:
            recommendation = "NEUTRAL"
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        analysis_markdown = str(data.get("analysis_markdown", "No critique provided."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from ML Analyst LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        recommendation = "NEUTRAL"
        confidence = 0.5
        analysis_markdown = f"Failed to parse LLM ML critique analysis. Raw response:\n\n{raw_content}"

    # 7. Save critique to database
    event = AgentMemoryEvent(
        agent_name="ml-analyst-agent",
        event_type="ml_analysis",
        key="latest_analysis",
        value_json={
            "prediction_probability": probability,
            "model_metadata": model_metadata,
            "recommendation": recommendation,
            "confidence": confidence,
            "analysis_markdown": analysis_markdown,
            "features": features_dict,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"ML Analyst critique completed. Event ID: {event.id}")
    return event
