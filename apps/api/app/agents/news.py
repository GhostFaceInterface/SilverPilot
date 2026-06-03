import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.gateway import DeepSeekGateway
from app.models.entities import RawNews, AgentMemoryEvent

logger = logging.getLogger("silverpilot.agents.news")


async def run_news_sentiment_analysis(db: Session) -> AgentMemoryEvent:
    """
    Fetches news from the last 24 hours (or the latest 10 as fallback),
    calls DeepSeek LLM to perform sentiment analysis,
    saves the results to AgentMemoryEvent, and returns the created event record.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # 1. Fetch news from the last 24 hours
    stmt = select(RawNews).where(RawNews.fetched_at >= twenty_four_hours_ago).order_by(desc(RawNews.fetched_at))
    news_items = db.execute(stmt).scalars().all()

    # 2. Fallback to latest 10 news articles if none found in 24 hours
    if not news_items:
        logger.info("No news articles found in the last 24 hours. Falling back to the latest 10 news articles.")
        stmt_fallback = select(RawNews).order_by(desc(RawNews.fetched_at)).limit(10)
        news_items = db.execute(stmt_fallback).scalars().all()

    # 3. On-demand live RSS fetch if database has no articles
    if not news_items:
        logger.info("No news in database. Attempting on-demand live RSS fetch...")
        try:
            from app.collectors.public_sources import RSS_FEEDS, collect_rss_news

            for feed_source, feed_urls in RSS_FEEDS.items():
                try:
                    _run, _inserted = collect_rss_news(db, source=feed_source, urls=feed_urls)
                    if _inserted > 0:
                        logger.info(f"On-demand RSS fetch: {feed_source} inserted {_inserted} articles.")
                except Exception as feed_err:
                    logger.warning(f"On-demand RSS fetch failed for {feed_source}: {feed_err}")

            # Re-query after on-demand fetch
            news_items = (
                db.execute(
                    select(RawNews)
                    .where(RawNews.fetched_at >= twenty_four_hours_ago)
                    .order_by(desc(RawNews.fetched_at))
                )
                .scalars()
                .all()
            )
        except Exception as fetch_all_err:
            logger.error(f"On-demand RSS fetch mechanism failed entirely: {fetch_all_err}")

    if not news_items:
        logger.warning("No news articles found in the database at all.")
        sentiment = "NEUTRAL"
        confidence = 0.0
        summary_markdown = "No recent news articles found in the database to analyze."

        event = AgentMemoryEvent(
            agent_name="news-agent",
            event_type="news_sentiment",
            key="latest_analysis",
            value_json={
                "sentiment": sentiment,
                "confidence": confidence,
                "summary_markdown": summary_markdown,
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 3. Format news titles, sources, and published times
    news_lines = []
    for item in news_items:
        pub_str = item.published_at.isoformat() if item.published_at else "N/A"
        news_lines.append(f"- Title: {item.title} | Source: {item.source} | Published At: {pub_str}")
    formatted_news = "\n".join(news_lines)

    # 4. Prepare prompt and call LLM via gateway
    settings = get_settings()
    model = settings.agent_news_model

    system_prompt = (
        "You are an expert financial analyst specializing in precious metals markets, particularly Silver (XAG).\n"
        "Analyze the provided list of recent news articles and evaluate their financial sentiment and potential "
        "impact on Silver (XAG) prices and precious metal markets.\n"
        "You must respond ONLY with a raw JSON object containing exactly the following keys:\n"
        '- "sentiment": string, must be one of "BULLISH", "BEARISH", or "NEUTRAL"\n'
        '- "confidence": float, a confidence score between 0.0 and 1.0 representing your certainty\n'
        '- "summary_markdown": string, a concise markdown summary of the news impact on Silver (XAG) prices '
        "and precious metal markets.\n\n"
        "Example response format:\n"
        "{\n"
        '  "sentiment": "BULLISH",\n'
        '  "confidence": 0.85,\n'
        '  "summary_markdown": "**Key Takeaways:**\\n- USD weakness continues to support precious metals.\\n- Silver demand is projected to rise due to solar industrial orders."\n'
        "}\n"
        "Provide ONLY the JSON response without markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = f"Analyze the following news articles:\n\n{formatted_news}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling News Agent LLM using model: {model} with {len(news_items)} news items.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="news-agent",
        model=model,
        messages=messages,
        temperature=0.2,
    )

    raw_content = response.get("content", "").strip()

    # Strip markdown code blocks if the model wrapped the JSON in them
    if raw_content.startswith("```"):
        lines = raw_content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_content = "\n".join(lines).strip()

    try:
        data = json.loads(raw_content)
        sentiment = str(data.get("sentiment", "NEUTRAL")).upper()
        if sentiment not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            sentiment = "NEUTRAL"
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        summary_markdown = str(data.get("summary_markdown", "Unable to extract summary."))
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from News Agent LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )
        sentiment = "NEUTRAL"
        confidence = 0.5
        summary_markdown = f"Failed to parse LLM analysis. Raw response:\n\n{raw_content}"

    # 5. Save the analysis results as an AgentMemoryEvent record
    event = AgentMemoryEvent(
        agent_name="news-agent",
        event_type="news_sentiment",
        key="latest_analysis",
        value_json={
            "sentiment": sentiment,
            "confidence": confidence,
            "summary_markdown": summary_markdown,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(f"News sentiment analysis completed and saved successfully. Event ID: {event.id}")
    return event
