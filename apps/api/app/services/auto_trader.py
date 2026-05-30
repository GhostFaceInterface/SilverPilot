import logging
import html
import re
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Bot

from app.core.config import get_settings
from app.models import Asset, PriceSnapshot, TechnicalIndicator, Portfolio, Signal, AgentMemoryEvent
from app.services.strategy import StrategyRunner
from app.paper_trading.service import execute_paper_trade, calculate_position
from app.schemas.paper_trading import PaperTradeRequest
from app.services.regime import get_market_regime
from app.agents.orchestrator import run_blended_consensus_resolution

logger = logging.getLogger("silverpilot.services.auto_trader")


def escape_html_response(text: str) -> str:
    """Escapes HTML special characters and converts markdown **bold** and *italic* to HTML tags."""
    if not text:
        return ""
    # Escape HTML special characters (&, <, >) first
    escaped = html.escape(text)
    # Safely convert double-asterisk bold to <b>...</b>
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
    # Safely convert single-asterisk italic to <i>...</i>
    escaped = re.sub(r"\*(.*?)\*", r"<i>\1</i>", escaped)
    return escaped


async def send_telegram_notification(trade_data: dict, settings, disable_notification: bool = False):
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram configuration missing. Notification skipped.")
        return

    # Check action to construct message
    action_str = ""
    status_emoji = ""
    action = trade_data["action"]
    if action == "paper_buy":
        action_str = "ALIM (BUY)"
        status_emoji = "🟢"
    elif action == "paper_sell":
        action_str = "SATIM (SELL)"
        status_emoji = "🔴"
    elif action == "blocked":
        action_str = "ENGELLENDİ (BLOCKED)"
        status_emoji = "⚠️"
    elif action == "HOLD":
        action_str = "BEKLE (HOLD)"
        status_emoji = "⚪️"
    else:
        # Unknown action
        return

    is_blended = trade_data.get("strategy_name") == "blended"

    if is_blended:
        regime_info = trade_data.get("regime_info", {})
        regime_label = "Yatay Sakin Piyasa (SIDEWAYS)"
        regime = regime_info.get("regime", "SIDEWAYS")
        if regime == "TRENDING_UP":
            regime_label = "Güçlü Yükseliş Trendi (TRENDING UP)"
        elif regime == "TRENDING_DOWN":
            regime_label = "Güçlü Düşüş Trendi (TRENDING DOWN)"

        votes = trade_data.get("strategy_votes", {})

        def format_vote(vote_dict):
            if not vote_dict:
                return "⚪️ BEKLE"
            act = vote_dict.get("action", "HOLD")
            reason = vote_dict.get("reason", "")
            reason_safe = html.escape(reason.replace("_", " ")) if reason else ""
            emoji = "🟢 AL" if act == "BUY" else ("🔴 SAT" if act == "SELL" else "⚪️ BEKLE")
            return f"{emoji} ({reason_safe})" if reason_safe else emoji

        rsi_vote = format_vote(votes.get("rsi"))
        bb_vote = format_vote(votes.get("bollinger"))
        sma_vote = format_vote(votes.get("sma_cross"))

        arbiter_stance = trade_data.get("arbiter_decision", "NEUTRAL")
        arbiter_emoji = (
            "🟢 AL" if arbiter_stance == "BULLISH" else ("🔴 SAT" if arbiter_stance == "BEARISH" else "⚪️ BEKLE")
        )
        arbiter_reason = escape_html_response(trade_data.get("arbiter_reason", "Gerekçe belirtilmedi."))

        msg = (
            f"📊 <b>SilverPilot Canlı Analiz Raporu</b>\n\n"
            f"🥈 <b>Gümüş (XAG_GRAM):</b> {trade_data['price']:,.4f} USD/gram\n"
            f"📈 <b>Piyasa Rejimi:</b> {regime_label}\n\n"
            f"🗳️ <b>Strateji Oylaması:</b>\n"
            f"• RSI (14): {rsi_vote}\n"
            f"• Bollinger Bands: {bb_vote}\n"
            f"• SMA Cross (20/50): {sma_vote}\n\n"
            f"👑 <b>Yüce Hakem Kararı:</b> {arbiter_emoji}\n"
            f"📝 <b>Gerekçe:</b> {arbiter_reason}\n\n"
            f"🔄 <b>İşlem Durumu:</b> {status_emoji} {action_str}\n"
        )

        if action in ("paper_buy", "paper_sell"):
            msg += (
                f"📦 <b>Miktar:</b> {trade_data.get('quantity', 0.0):,.4f} XAG_GRAM\n"
                f"💰 <b>Net Tutar:</b> {trade_data.get('net_amount', 0.0):,.2f} USD\n"
            )

        msg += f"💵 <b>Nakit Bakiyesi:</b> {trade_data.get('cash_balance', 0.0):,.2f} USD\n"
        if "xag_balance" in trade_data:
            msg += f"🥈 <b>Gümüş Portföyü:</b> {trade_data['xag_balance']:,.4f} XAG_GRAM\n"

        risk_decision = trade_data.get("risk_decision")
        if risk_decision:
            msg += (
                f"\n⚖️ <b>Risk Kararı:</b> {risk_decision['decision'].upper()}\n"
                f"🔍 <b>Neden Kodu:</b> <code>{html.escape(risk_decision['reason_code'])}</code>\n"
                f"📊 <b>Risk Seviyesi:</b> {risk_decision['risk_level']}\n"
            )
    else:
        risk_info = ""
        risk_decision = trade_data.get("risk_decision")
        if risk_decision:
            risk_info = (
                f"\n⚖️ <b>Risk Kararı:</b> {risk_decision['decision'].upper()}\n"
                f"🔍 <b>Neden Kodu:</b> <code>{html.escape(risk_decision['reason_code'])}</code>\n"
                f"📊 <b>Risk Seviyesi:</b> {risk_decision['risk_level']}\n"
            )

        indicator_details = ""
        indicators = trade_data.get("indicators", {})
        if indicators:
            indicator_details = (
                f"\n📊 <b>Teknik Göstergeler:</b>\n"
                f"• RSI (14): {indicators.get('rsi', 0.0):,.2f}\n"
                f"• SMA (20/50): {indicators.get('sma_20', 0.0):,.2f} / {indicators.get('sma_50', 0.0):,.2f}\n"
                f"• Bollinger (U/L): {indicators.get('bb_upper', 0.0):,.2f} / {indicators.get('bb_lower', 0.0):,.2f}\n"
            )

        regime_info = trade_data.get("regime_info", {})
        regime_details = ""
        if regime_info:
            regime = regime_info.get("regime", "SIDEWAYS")
            regime_label = "Yatay Sakin Piyasa (SIDEWAYS)"
            if regime == "TRENDING_UP":
                regime_label = "Güçlü Yükseliş Trendi (TRENDING UP)"
            elif regime == "TRENDING_DOWN":
                regime_label = "Güçlü Düşüş Trendi (TRENDING DOWN)"
            regime_details = f"📈 <b>Piyasa Rejimi:</b> {regime_label}\n"

        msg = (
            f"{status_emoji} <b>SilverPilot Auto-Trading Raporu</b>\n\n"
            f"🔄 <b>İşlem Tipi:</b> {action_str}\n"
            f"🥈 <b>Varlık:</b> XAG_GRAM (Gümüş)\n"
            f"🏷️ <b>Fiyat:</b> {trade_data['price']:,.4f} USD/gram\n"
            f"{regime_details}"
        )
        if action in ("paper_buy", "paper_sell", "blocked"):
            msg += (
                f"📦 <b>Miktar:</b> {trade_data.get('quantity', 0.0):,.4f} XAG_GRAM\n"
                f"💰 <b>Net Tutar:</b> {trade_data.get('net_amount', 0.0):,.2f} USD\n"
                f"💸 <b>Komisyon (Fees):</b> {trade_data.get('fees', 0.0):,.2f} USD\n"
            )
        msg += f"💵 <b>Nakit Bakiyesi:</b> {trade_data.get('cash_balance', 0.0):,.2f} USD\n"
        msg += f"{indicator_details}{risk_info}"

    import asyncio
    from telegram.error import RetryAfter, TelegramError

    attempts = 3
    backoff = 2.0
    for attempt in range(1, attempts + 1):
        try:
            bot = Bot(token=settings.telegram_bot_token)
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=msg,
                parse_mode="HTML",
                disable_notification=disable_notification,
            )
            logger.info(
                f"Telegram notification sent successfully (silent={disable_notification}, attempt {attempt}/{attempts})."
            )
            return
        except RetryAfter as e:
            from datetime import timedelta

            seconds = e.retry_after.total_seconds() if isinstance(e.retry_after, timedelta) else float(e.retry_after)
            wait_time = seconds + 1.0
            if attempt == attempts:
                logger.error(
                    f"Failed to send Telegram notification due to rate limits after {attempts} attempts.", exc_info=True
                )
                break
            logger.warning(
                f"Telegram rate limit hit (RetryAfter). Waiting {wait_time}s before retry (attempt {attempt}/{attempts})..."
            )
            await asyncio.sleep(wait_time)
        except TelegramError as e:
            if attempt == attempts:
                logger.error(f"Failed to send Telegram notification after {attempts} attempts: {e}", exc_info=True)
                break
            wait_time = backoff * attempt
            logger.warning(f"Telegram API error: {e}. Retrying in {wait_time}s (attempt {attempt}/{attempts})...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            if attempt == attempts:
                logger.error(
                    f"Unexpected connection error sending Telegram notification after {attempts} attempts: {e}",
                    exc_info=True,
                )
                break
            wait_time = backoff * attempt
            logger.warning(
                f"Connection error sending Telegram notification: {e}. Retrying in {wait_time}s (attempt {attempt}/{attempts})..."
            )
            await asyncio.sleep(wait_time)


async def run_auto_trading(db: Session = None):
    logger.info("Starting run_auto_trading evaluation...")
    settings = get_settings()

    if not settings.auto_trading_enabled:
        logger.info("Auto trading is disabled in settings.")
        return

    if db is not None:
        try:
            await _run_auto_trading_impl(db, settings)
        except Exception as e:
            db.rollback()
            logger.error(f"Auto trading loop encountered a fatal exception on shared session: {e}", exc_info=True)
            raise e
    else:
        from app.core.db import SessionLocal

        db_session = SessionLocal()
        try:
            await _run_auto_trading_impl(db_session, settings)
        except Exception as e:
            db_session.rollback()
            logger.error(f"Auto trading loop encountered a fatal exception: {e}", exc_info=True)
        finally:
            db_session.close()


async def _run_auto_trading_impl(db: Session, settings):
    # 0. Pazartesi Isınma Süresi Kontrolü (Indicator Warmup)
    # Pazar 18:00 - 18:05 ET arası (piyasa açılışının ilk 5 dakikası) işlemler ertelenir
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(timezone.utc).astimezone(et_tz)
    if now_et.weekday() == 6 and now_et.hour == 18 and now_et.minute < 5:
        logger.info(
            "COMEX market opening warmup window active (Sunday 18:00-18:05 ET). Holding trading to let indicators heat up."
        )
        return

    # 1. Fetch portfolio 'gram-paper'
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    if not portfolio:
        logger.error("Portfolio 'gram-paper' not found")
        return

    # 2. Fetch asset 'XAG_GRAM'
    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        logger.error("Asset 'XAG_GRAM' not found")
        return

    # 3. Fetch two latest indicators from any global source for XAG_GRAM
    stmt = (
        select(TechnicalIndicator)
        .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
        .where(
            PriceSnapshot.source.in_(["yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"]),
            PriceSnapshot.asset_id == asset.id,
        )
        .order_by(TechnicalIndicator.bar_timestamp.desc())
        .limit(2)
    )
    indicators = db.execute(stmt).scalars().all()
    if not indicators:
        logger.warning("No technical indicators found for XAG_GRAM from any global source")
        return

    latest_indicator = indicators[0]
    prev_indicator = indicators[1] if len(indicators) > 1 else None

    # Get matching PriceSnapshot for the latest indicator
    latest_snapshot = latest_indicator.price_snapshot
    if not latest_snapshot:
        latest_snapshot = db.execute(
            select(PriceSnapshot).where(PriceSnapshot.id == latest_indicator.price_snapshot_id)
        ).scalar_one_or_none()

    if not latest_snapshot:
        logger.error(f"PriceSnapshot not found for indicator ID {latest_indicator.id}")
        return

    # Get position status
    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0

    regime_info = {}
    strategy_votes = {}
    resolved_stance = "NEUTRAL"
    resolution_markdown = "Standard Strategy Selected."

    # 4. Evaluate strategy
    if settings.strategy_name == "blended":
        regime_info = get_market_regime(db)
        strategy_votes = StrategyRunner.evaluate_blended_strategies(
            close=latest_indicator.close_usd_oz,
            rsi_14=latest_indicator.rsi_14,
            sma_20=latest_indicator.sma_20,
            sma_50=latest_indicator.sma_50,
            prev_sma_20=prev_indicator.sma_20 if prev_indicator else None,
            prev_sma_50=prev_indicator.sma_50 if prev_indicator else None,
            bb_lower=latest_indicator.bb_lower_20_2,
            bb_upper=latest_indicator.bb_upper_20_2,
            has_open_position=has_open_position,
        )
        # Call Supreme Consensus Engine
        consensus_event = await run_blended_consensus_resolution(db, regime_info, strategy_votes, latest_snapshot)
        resolved_stance = consensus_event.value_json.get("resolved_stance", "NEUTRAL")
        resolution_markdown = consensus_event.value_json.get("resolution_markdown", "No details.")

        # Map stance to action: BULLISH -> BUY, BEARISH -> SELL, NEUTRAL -> HOLD
        if resolved_stance == "BULLISH":
            action = "BUY"
        elif resolved_stance == "BEARISH":
            action = "SELL"
        else:
            action = "HOLD"
        reason_code = f"BLENDED_{resolved_stance}"
    else:
        action, reason_code = StrategyRunner.evaluate_all_strategies(
            close=latest_indicator.close_usd_oz,
            rsi_14=latest_indicator.rsi_14,
            sma_20=latest_indicator.sma_20,
            sma_50=latest_indicator.sma_50,
            prev_sma_20=prev_indicator.sma_20 if prev_indicator else None,
            prev_sma_50=prev_indicator.sma_50 if prev_indicator else None,
            bb_lower=latest_indicator.bb_lower_20_2,
            bb_upper=latest_indicator.bb_upper_20_2,
            has_open_position=has_open_position,
            strategy_name=settings.strategy_name,
        )

    logger.info(f"Strategy evaluation: action={action}, reason={reason_code}")

    # Retrieve news_sentiment: fetch latest 'news-agent' or 'hermes-agent' event from db, defaulting to 'NEUTRAL'
    news_sentiment = "NEUTRAL"
    latest_event = db.execute(
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.agent_name.in_(["news-agent", "hermes-agent"]))
        .order_by(AgentMemoryEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if latest_event and latest_event.value_json:
        news_sentiment = latest_event.value_json.get("sentiment", "NEUTRAL")

    risk_decision_val = "APPROVED"

    filtered_action, filter_reason = StrategyRunner.apply_agent_filters(
        action=action,
        news_sentiment=news_sentiment,
        risk_decision=risk_decision_val,
        db=db,
    )
    if filtered_action != action:
        logger.info(f"Agent filters vetoed action {action} -> {filtered_action} (reason: {filter_reason})")
        action = filtered_action
        reason_code = filter_reason

    # 5. Create Signal record
    details = {
        "strategy_name": settings.strategy_name,
        "rsi_14": float(latest_indicator.rsi_14) if latest_indicator.rsi_14 is not None else None,
        "sma_20": float(latest_indicator.sma_20) if latest_indicator.sma_20 is not None else None,
        "sma_50": float(latest_indicator.sma_50) if latest_indicator.sma_50 is not None else None,
        "bb_lower": float(latest_indicator.bb_lower_20_2) if latest_indicator.bb_lower_20_2 is not None else None,
        "bb_upper": float(latest_indicator.bb_upper_20_2) if latest_indicator.bb_upper_20_2 is not None else None,
    }
    if settings.strategy_name == "blended":
        details.update(
            {
                "regime_info": regime_info,
                "strategy_votes": strategy_votes,
                "arbiter_decision": resolved_stance,
                "arbiter_reason": resolution_markdown,
            }
        )

    signal = Signal(
        observed_at=latest_snapshot.observed_at,
        price_snapshot_id=latest_snapshot.id,
        indicator_id=latest_indicator.id,
        action=action,
        reason_code=reason_code,
        price_usd_oz=latest_snapshot.mid_price,
        details_json=details,
    )
    db.add(signal)
    db.flush()

    trade = None
    buy_price = latest_snapshot.buy_price if latest_snapshot.buy_price else latest_snapshot.mid_price
    sell_price = latest_snapshot.sell_price if latest_snapshot.sell_price else latest_snapshot.mid_price

    # 6. Trade execution
    if action == "BUY" and not has_open_position:
        cash = portfolio.cash_balance
        if cash > Decimal("0.05"):
            request = PaperTradeRequest(
                portfolio_name="gram-paper",
                asset_symbol="XAG_GRAM",
                action="paper_buy",
                quantity=None,
                cash_amount=cash,
                buy_price=buy_price,
                sell_price=sell_price,
                fees=Decimal("0.05"),
                taxes=Decimal("0"),
            )
            original_commit = db.commit
            db.commit = db.flush
            try:
                with db.begin_nested():
                    trade, snapshot = execute_paper_trade(db, request)
                logger.info(f"Auto trader BUY executed: trade_id={trade.id}, status={trade.action}")
            except Exception:
                logger.exception("Failed to execute auto trader BUY")
            finally:
                db.commit = original_commit
        else:
            logger.warning(f"Insufficient cash balance to buy: {cash}")

    elif action == "SELL" and has_open_position:
        request = PaperTradeRequest(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="paper_sell",
            quantity=current_position.quantity,
            buy_price=buy_price,
            sell_price=sell_price,
            fees=Decimal("0.05"),
            taxes=Decimal("0"),
        )
        original_commit = db.commit
        db.commit = db.flush
        try:
            with db.begin_nested():
                trade, snapshot = execute_paper_trade(db, request)
            logger.info(f"Auto trader SELL executed: trade_id={trade.id}, status={trade.action}")
        except Exception:
            logger.exception("Failed to execute auto trader SELL")
        finally:
            db.commit = original_commit

    # 7. Extract notification data prior to commit/close to avoid DetachedInstanceError
    notification_data = {
        "action": trade.action if trade else action,
        "price": float(trade.price) if trade else float(latest_snapshot.mid_price),
        "quantity": float(trade.quantity) if trade else 0.0,
        "net_amount": float(trade.net_amount) if trade else 0.0,
        "fees": float(trade.fees) if trade else 0.0,
        "cash_balance": float(portfolio.cash_balance),
        "xag_balance": float(current_position.quantity),
        "strategy_name": settings.strategy_name,
        "indicators": {
            "rsi": float(latest_indicator.rsi_14) if latest_indicator.rsi_14 is not None else 0.0,
            "sma_20": float(latest_indicator.sma_20) if latest_indicator.sma_20 is not None else 0.0,
            "sma_50": float(latest_indicator.sma_50) if latest_indicator.sma_50 is not None else 0.0,
            "bb_upper": float(latest_indicator.bb_upper_20_2) if latest_indicator.bb_upper_20_2 is not None else 0.0,
            "bb_lower": float(latest_indicator.bb_lower_20_2) if latest_indicator.bb_lower_20_2 is not None else 0.0,
        },
        "risk_decision": {
            "decision": trade.risk_decision.decision,
            "reason_code": trade.risk_decision.reason_code,
            "risk_level": trade.risk_decision.risk_level,
        }
        if (trade and trade.risk_decision)
        else None,
    }

    if settings.strategy_name == "blended":
        notification_data.update(
            {
                "regime_info": regime_info,
                "strategy_votes": strategy_votes,
                "arbiter_decision": resolved_stance,
                "arbiter_reason": resolution_markdown,
            }
        )

    # Commit transactions
    db.commit()

    # 8. Send Telegram message
    is_silent = notification_data["action"] == "HOLD"
    await send_telegram_notification(notification_data, settings, disable_notification=is_silent)
