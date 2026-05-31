import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.gateway import DeepSeekGateway
from app.models.entities import RawNews, AgentMemoryEvent
from app.services.telegram import send_telegram_message

logger = logging.getLogger("silverpilot.agents.hermes")

TARGET_SOURCES = {
    "kitco-rss",
    "bloomberght-rss",
    "fxstreet-rss",
    "gcm-yatirim",
    "yahoo-usd-try",
    "federal-reserve-rss",
    "investing",
    "investing-rss",
}


async def run_hermes_sentiment_analysis(db: Session) -> AgentMemoryEvent:
    """
    Fetches recent news from RawNews in the last 24 hours (or falls back to the latest 15 matching sources).
    Calls DeepSeek LLM to perform multi-aspect sentiment, relevance, and speculation calculations.
    Computes a weighted final score in the range [-1.0, 1.0] using configured source weights.
    Saves the results as an AgentMemoryEvent and returns the created event.
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    # 1. Fetch recent news matching target sources from the last 24 hours
    stmt = (
        select(RawNews)
        .where(RawNews.fetched_at >= twenty_four_hours_ago, RawNews.source.in_(list(TARGET_SOURCES)))
        .order_by(desc(RawNews.fetched_at))
    )
    news_items = db.execute(stmt).scalars().all()

    # 2. Fallback to latest 15 news matching sources if none found in last 24 hours
    if not news_items:
        logger.info(
            "No matching source news in the last 24 hours. Falling back to the latest 15 matching source news articles."
        )
        stmt_fallback = (
            select(RawNews).where(RawNews.source.in_(list(TARGET_SOURCES))).order_by(desc(RawNews.fetched_at)).limit(15)
        )
        news_items = db.execute(stmt_fallback).scalars().all()

    # 3. Fallback to any latest 15 news if no source-matched articles found at all
    if not news_items:
        logger.info("No source-matched news found in the database. Falling back to any latest 15 news articles.")
        stmt_any = select(RawNews).order_by(desc(RawNews.fetched_at)).limit(15)
        news_items = db.execute(stmt_any).scalars().all()

    if not news_items:
        logger.warning("No news articles found in the database at all.")
        event = AgentMemoryEvent(
            agent_name="hermes-agent",
            event_type="hermes_sentiment",
            key="latest_analysis",
            value_json={
                "score": 0.0,
                "sentiment": "NEUTRAL",
                "articles": [],
                "summary_markdown": "No news articles found in the database to analyze.",
                "analyzed_at": now.isoformat(),
            },
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # 4. Format news titles, sources, and published times
    news_lines = []
    for item in news_items:
        pub_str = item.published_at.isoformat() if item.published_at else "N/A"
        news_lines.append(f"- Title: {item.title} | Source: {item.source} | Published At: {pub_str}")
    formatted_news = "\n".join(news_lines)

    # 5. Prepare prompt and call LLM via gateway
    settings = get_settings()
    model = settings.agent_hermes_model

    system_prompt = (
        "You are Hermes, a precision sentiment analysis agent specializing in precious metals markets, particularly Silver (XAG), and macro-financial markets.\n"
        "Analyze the provided list of recent news articles. For each article, perform multi-aspect sentiment, relevance, and speculation calculations.\n"
        "You must respond ONLY with a raw JSON array of news analyses. Each analysis in the array MUST correspond exactly to the articles list in order, containing exactly the following keys:\n"
        '- "title": string, the title of the article analyzed\n'
        '- "sentiment": string, must be one of "BULLISH", "BEARISH", or "NEUTRAL"\n'
        '- "relevance": float between 0.0 and 1.0 (closeness to Silver market / macro factors like USD, rate decisions, inflation, industrial demand)\n'
        '- "speculation": float between 0.0 and 1.0 (clickbait, sensationalism, or rumor score)\n\n'
        "Example response format:\n"
        "[\n"
        "  {\n"
        '    "title": "Fed leaves interest rates unchanged",\n'
        '    "sentiment": "NEUTRAL",\n'
        '    "relevance": 0.90,\n'
        '    "speculation": 0.10\n'
        "  },\n"
        "  {\n"
        '    "title": "Silver price set to triple tomorrow says popular blog",\n'
        '    "sentiment": "BULLISH",\n'
        '    "relevance": 0.70,\n'
        '    "speculation": 0.95\n'
        "  }\n"
        "]\n"
        "Provide ONLY the raw JSON array response. Do not include markdown code blocks, text wrapper, or explanations."
    )

    user_prompt = f"Analyze the following news articles:\n\n{formatted_news}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Hermes Agent LLM using model: {model} with {len(news_items)} news items.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="hermes-agent",
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

    parsed_list = []
    try:
        parsed_list = json.loads(raw_content)
        if not isinstance(parsed_list, list):
            logger.warning("Parsed response is not a JSON array. Recovering to empty list.")
            parsed_list = []
    except Exception as parse_err:
        logger.warning(
            f"Failed to parse JSON from Hermes Agent LLM response. Raw content: {raw_content}. Error: {parse_err}"
        )

    # If parsing failed or returned empty list, recover by creating a neutral fallback entry for each article
    if not parsed_list:
        parsed_list = [
            {"title": item.title, "sentiment": "NEUTRAL", "relevance": 0.5, "speculation": 0.5} for item in news_items
        ]

    # 6. Calculate the Weighted Sentiment Score
    total_weighted_score = 0.0
    total_source_weight = 0.0
    analyzed_articles = []

    for idx, parsed in enumerate(parsed_list):
        # Retrieve the original news item to extract the real source
        source_name = "unknown"
        if idx < len(news_items):
            source_name = news_items[idx].source
        elif len(news_items) > 0:
            source_name = news_items[0].source  # fallback safely

        source_lower = source_name.lower() if source_name else ""
        if any(s in source_lower for s in ["kitco", "fxstreet", "reuters", "fed", "federal"]):
            source_weight = float(settings.weight_global_authority)
        elif any(s in source_lower for s in ["gcm", "bloomberght", "bloomberg"]):
            source_weight = float(settings.weight_local_expert)
        elif "investing" in source_lower:
            source_weight = float(settings.weight_local_forum)
        else:
            source_weight = float(settings.weight_global_authority)

        sentiment_label = str(parsed.get("sentiment", "NEUTRAL")).upper()
        if sentiment_label == "BULLISH":
            sentiment_numeric = 1.0
        elif sentiment_label == "BEARISH":
            sentiment_numeric = -1.0
        else:
            sentiment_numeric = 0.0

        relevance = float(parsed.get("relevance", 0.5))
        speculation = float(parsed.get("speculation", 0.5))

        # Clamp calculations safely
        relevance = max(0.0, min(1.0, relevance))
        speculation = max(0.0, min(1.0, speculation))

        article_score = sentiment_numeric * (1.0 - speculation) * relevance * source_weight

        total_weighted_score += article_score
        total_source_weight += source_weight

        analyzed_articles.append(
            {
                "title": parsed.get("title", ""),
                "source": source_name,
                "sentiment": sentiment_label,
                "relevance": relevance,
                "speculation": speculation,
                "article_score": article_score,
                "source_weight": source_weight,
            }
        )

    final_score = total_weighted_score / total_source_weight if total_source_weight > 0.0 else 0.0
    veto_threshold = float(settings.hermes_veto_threshold)

    # Determine final sentiment label based on thresholds
    if final_score < veto_threshold:
        final_sentiment = "BEARISH"
    elif final_score >= 0.15:
        final_sentiment = "BULLISH"
    else:
        final_sentiment = "NEUTRAL"

    # Generate summary markdown report
    summary_markdown = (
        f"### 🏛️ Hermes Sentiment Analysis Report\n\n"
        f"- **Overall Score**: `{final_score:.4f}` (Range: [-1.0, 1.0])\n"
        f"- **Resolved Sentiment**: `{final_sentiment}`\n"
        f"- **Veto Threshold**: `{veto_threshold}`\n\n"
        f"| Article Title | Source | Sentiment | Relevance | Speculation | Article Score |\n"
        f"| :--- | :--- | :---: | :---: | :---: | :---: |\n"
    )
    for art in analyzed_articles:
        summary_markdown += (
            f"| {art['title']} | `{art['source']}` | **{art['sentiment']}** | "
            f"`{art['relevance']:.2f}` | `{art['speculation']:.2f}` | `{art['article_score']:.4f}` |\n"
        )

    # 7. Save to AgentMemoryEvent
    event = AgentMemoryEvent(
        agent_name="hermes-agent",
        event_type="hermes_sentiment",
        key="latest_analysis",
        value_json={
            "score": final_score,
            "sentiment": final_sentiment,
            "articles": analyzed_articles,
            "weights": {
                "global_authority": float(settings.weight_global_authority),
                "local_expert": float(settings.weight_local_expert),
                "local_forum": float(settings.weight_local_forum),
            },
            "summary_markdown": summary_markdown,
            "analyzed_at": now.isoformat(),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # 8. Hafta Sonu Telegram Bildirim Entegrasyonu
    try:
        from app.risk.service import is_comex_market_closed

        if is_comex_market_closed(now) and settings.telegram_bot_token and settings.telegram_chat_id:
            telegram_text = (
                f"🏛️ <b>SilverPilot Hafta Sonu Nöbetçi Raporu</b>\n\n"
                f"Geçtiğimiz 6 saat boyunca gelen makroekonomik haberler analiz edildi:\n\n"
                f"📊 <b>Genel Sentiment Skoru:</b> <code>{final_score:.4f}</code>\n"
                f"🎯 <b>Karar:</b> <b>{final_sentiment}</b>\n"
                f"📰 <b>İncelenen Haber Sayısı:</b> {len(analyzed_articles)} adet\n\n"
                f"💡 <i>Pazartesi açılış emri hazırlığı için nöbetçi mod aktif olarak haber akışını izlemeye devam ediyor.</i>"
            )

            await send_telegram_message(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
                text=telegram_text,
                parse_mode="HTML",
            )

            logger.info("Telegram weekend sentiment report sent successfully.")
    except Exception as telegram_err:
        logger.error(f"Failed to send Telegram weekend sentiment report: {telegram_err}", exc_info=True)

    logger.info(
        f"Hermes weighted sentiment analysis completed and saved successfully. Event ID: {event.id}, Score: {final_score:.4f}"
    )
    return event
