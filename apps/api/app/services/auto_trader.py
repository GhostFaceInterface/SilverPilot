import logging
import html
import re
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Portfolio, Signal, AgentMemoryEvent
from app.services.strategy import StrategyRunner
from app.paper_trading.service import calculate_position
from app.services.indicator_readiness import get_latest_indicator_context
from app.services.trade_intents import TradeIntent, execute_trade_intent

logger = logging.getLogger("silverpilot.services.auto_trader")

STRATEGY_TIMEFRAME_POLICY = {
    "1d": 48 * 60,
    "1h": 3 * 60,
    "5m": 20,
}


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

    from app.services.telegram import send_telegram_message

    try:
        await send_telegram_message(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            text=msg,
            parse_mode="HTML",
            disable_notification=disable_notification,
        )
    except Exception as e:
        logger.error("Failed to dispatch trade Telegram notification; error_type=%s.", type(e).__name__)


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
    from datetime import timezone
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

    timeframe_contexts = get_strategy_timeframe_contexts(db, asset.symbol)
    daily_context = timeframe_contexts["1d"]
    hourly_context = timeframe_contexts["1h"]
    execution_context = timeframe_contexts["5m"]
    strategy_readiness_flags = evaluate_timeframe_guardrails(timeframe_contexts, ref_dt=datetime.now(UTC))

    latest_indicator = hourly_context.readiness.indicator
    execution_indicator = execution_context.readiness.indicator

    latest_snapshot = execution_indicator.price_snapshot if execution_indicator is not None else None
    if not latest_snapshot:
        from app.models import PriceSnapshot

        latest_snapshot_id = execution_context.readiness.price_snapshot_id or hourly_context.readiness.price_snapshot_id
        if latest_snapshot_id is not None:
            latest_snapshot = db.execute(
                select(PriceSnapshot).where(PriceSnapshot.id == latest_snapshot_id)
            ).scalar_one_or_none()

    if not latest_snapshot:
        logger.error("PriceSnapshot not found for strategy execution.")
        return

    # Get position status
    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0

    # Retrieve latest 'hermes-agent' memory event from db
    latest_event = db.execute(
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.agent_name == "hermes-agent")
        .order_by(AgentMemoryEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    news_sentiment = "NEUTRAL"
    if latest_event and latest_event.value_json:
        news_sentiment = latest_event.value_json.get("sentiment", "NEUTRAL")

    # 4. Evaluate strategy based on config routing.
    active_strategy = settings.strategy_name or "strategy_v2"
    action = "HOLD"
    reason_code = "UNKNOWN"
    confidence = Decimal("0.5000")
    stop_loss_price = None
    take_profit_price = None
    expected_exit_price = None
    details = {}

    has_block_flag = False
    block_reason = None
    if "TIMEFRAME_SOURCE_MISMATCH" in strategy_readiness_flags:
        block_reason = "TIMEFRAME_SOURCE_MISMATCH"
        has_block_flag = True
    elif "ENTRY_TIMEFRAME_STALE" in strategy_readiness_flags:
        block_reason = "ENTRY_TIMEFRAME_STALE"
        has_block_flag = True
    elif "ENTRY_TIMEFRAME_UNUSABLE" in strategy_readiness_flags:
        block_reason = "ENTRY_TIMEFRAME_UNUSABLE"
        has_block_flag = True
    elif "DAILY_TREND_MISSING" in strategy_readiness_flags:
        block_reason = "DAILY_TREND_MISSING"
        has_block_flag = True
    elif "EXECUTION_TIMEFRAME_STALE" in strategy_readiness_flags:
        block_reason = "EXECUTION_TIMEFRAME_STALE"
        has_block_flag = True
    elif "EXECUTION_TIMEFRAME_UNUSABLE" in strategy_readiness_flags:
        block_reason = "EXECUTION_TIMEFRAME_UNUSABLE"
        has_block_flag = True

    if has_block_flag:
        action = "HOLD"
        reason_code = block_reason
        if block_reason == "TIMEFRAME_SOURCE_MISMATCH":
            confidence = Decimal("0.9900")
        elif block_reason in ("ENTRY_TIMEFRAME_STALE", "ENTRY_TIMEFRAME_UNUSABLE"):
            confidence = Decimal("0.9800")
        elif block_reason == "DAILY_TREND_MISSING":
            confidence = Decimal("0.9900")
        else:
            confidence = Decimal("0.9700")

        details = {
            "strategy_name": active_strategy,
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            "readiness_block_flags": strategy_readiness_flags,
        }
    elif active_strategy == "blended":
        from app.services.regime import get_market_regime
        from app.agents.orchestrator import run_blended_consensus_resolution

        regime_info = get_market_regime(db, asset_symbol=asset.symbol, timeframe=hourly_context.readiness.timeframe)

        close = latest_indicator.close_usd_oz if latest_indicator else None
        rsi_14 = latest_indicator.rsi_14 if latest_indicator else None
        sma_20 = latest_indicator.sma_20 if latest_indicator else None
        sma_50 = latest_indicator.sma_50 if latest_indicator else None
        prev_sma_20 = (
            hourly_context.previous_indicator.sma_20
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        prev_sma_50 = (
            hourly_context.previous_indicator.sma_50
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        bb_lower = latest_indicator.bb_lower_20_2 if latest_indicator else None
        bb_upper = latest_indicator.bb_upper_20_2 if latest_indicator else None

        strategy_votes = StrategyRunner.evaluate_blended_strategies(
            close=close,
            rsi_14=rsi_14,
            sma_20=sma_20,
            sma_50=sma_50,
            prev_sma_20=prev_sma_20,
            prev_sma_50=prev_sma_50,
            bb_lower=bb_lower,
            bb_upper=bb_upper,
            has_open_position=has_open_position,
        )

        consensus_event = await run_blended_consensus_resolution(
            db=db,
            regime_info=regime_info,
            strategy_votes=strategy_votes,
            latest_snapshot=latest_snapshot,
            hermes_sentiment=latest_event.value_json if latest_event else None,
        )

        resolved_stance = consensus_event.value_json.get("resolved_stance", "NEUTRAL")
        confidence = Decimal(str(consensus_event.value_json.get("confidence", "0.5")))
        resolution_markdown = consensus_event.value_json.get("resolution_markdown", "")

        if resolved_stance == "BULLISH":
            if not has_open_position:
                action = "BUY"
                reason_code = "BLENDED_BULLISH"
            else:
                action = "HOLD"
                reason_code = "BLENDED_BULLISH_BUT_POSITION_OPEN"
        elif resolved_stance == "BEARISH":
            if has_open_position:
                action = "SELL"
                reason_code = "BLENDED_BEARISH"
            else:
                action = "HOLD"
                reason_code = "BLENDED_BEARISH_BUT_NO_POSITION"
        else:
            action = "HOLD"
            reason_code = "BLENDED_NEUTRAL"

        atr_value = (
            Decimal(str(latest_indicator.atr_14))
            if (latest_indicator and latest_indicator.atr_14 is not None)
            else None
        )
        close_value = (
            Decimal(str(latest_indicator.close_usd_oz))
            if (latest_indicator and latest_indicator.close_usd_oz is not None)
            else None
        )
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        details = {
            "strategy_name": "blended",
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            "regime_info": regime_info,
            "strategy_votes": strategy_votes,
            "arbiter_decision": resolved_stance,
            "arbiter_reason": resolution_markdown,
            "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
            "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
            "expected_exit_price": float(expected_exit_price) if expected_exit_price is not None else None,
        }

    elif active_strategy in ("rsi", "sma_cross", "bollinger"):
        close = latest_indicator.close_usd_oz if latest_indicator else None
        rsi_14 = latest_indicator.rsi_14 if latest_indicator else None
        sma_20 = latest_indicator.sma_20 if latest_indicator else None
        sma_50 = latest_indicator.sma_50 if latest_indicator else None
        prev_sma_20 = (
            hourly_context.previous_indicator.sma_20
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        prev_sma_50 = (
            hourly_context.previous_indicator.sma_50
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        bb_lower = latest_indicator.bb_lower_20_2 if latest_indicator else None
        bb_upper = latest_indicator.bb_upper_20_2 if latest_indicator else None

        action, reason_code = StrategyRunner.evaluate_all_strategies(
            close=close,
            rsi_14=rsi_14,
            sma_20=sma_20,
            sma_50=sma_50,
            prev_sma_20=prev_sma_20,
            prev_sma_50=prev_sma_50,
            bb_lower=bb_lower,
            bb_upper=bb_upper,
            has_open_position=has_open_position,
            strategy_name=active_strategy,
        )
        confidence = Decimal("0.9000")

        atr_value = (
            Decimal(str(latest_indicator.atr_14))
            if (latest_indicator and latest_indicator.atr_14 is not None)
            else None
        )
        close_value = (
            Decimal(str(latest_indicator.close_usd_oz))
            if (latest_indicator and latest_indicator.close_usd_oz is not None)
            else None
        )
        if atr_value is not None and close_value is not None:
            risk_unit = max(atr_value * Decimal("1.5"), close_value * Decimal("0.01"))
            reward_unit = max(atr_value * Decimal("2.5"), close_value * Decimal("0.015"))
            stop_loss_price = close_value - risk_unit
            take_profit_price = close_value + reward_unit
            expected_exit_price = take_profit_price

        details = {
            "strategy_name": active_strategy,
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
            "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
            "expected_exit_price": float(expected_exit_price) if expected_exit_price is not None else None,
        }

    else:
        if latest_indicator is None or daily_context.readiness.indicator is None:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            strategy_decision = StrategyRunner.evaluate_strategy_v2(
                daily_close=None,
                daily_sma_20=None,
                daily_sma_50=None,
                entry_close=None,
                entry_rsi_14=None,
                entry_sma_20=None,
                entry_sma_50=None,
                entry_macd_histogram=None,
                entry_bb_middle=None,
                entry_atr_14=None,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )
        else:
            execution_ready = "EXECUTION_TIMEFRAME_STALE" not in strategy_readiness_flags
            strategy_decision = StrategyRunner.evaluate_strategy_v2(
                daily_close=daily_context.readiness.indicator.close_usd_oz,
                daily_sma_20=daily_context.readiness.indicator.sma_20,
                daily_sma_50=daily_context.readiness.indicator.sma_50,
                entry_close=latest_indicator.close_usd_oz,
                entry_rsi_14=latest_indicator.rsi_14,
                entry_sma_20=latest_indicator.sma_20,
                entry_sma_50=latest_indicator.sma_50,
                entry_macd_histogram=latest_indicator.macd_histogram,
                entry_bb_middle=latest_indicator.bb_middle_20_2,
                entry_atr_14=latest_indicator.atr_14,
                has_open_position=has_open_position,
                execution_ready=execution_ready,
                readiness_block_flags=strategy_readiness_flags,
            )

        action = strategy_decision.action
        reason_code = strategy_decision.reason_code
        confidence = strategy_decision.confidence
        stop_loss_price = strategy_decision.stop_loss_price
        take_profit_price = strategy_decision.take_profit_price
        expected_exit_price = strategy_decision.expected_exit_price

        details = {
            "strategy_name": "strategy_v2",
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            **strategy_decision.to_signal_details(),
        }

    logger.info("Strategy %s evaluation: action=%s reason=%s.", active_strategy, action, reason_code)

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

    details["agent_filter_reason"] = filter_reason or None

    signal = Signal(
        observed_at=latest_snapshot.observed_at,
        price_snapshot_id=latest_snapshot.id,
        indicator_id=latest_indicator.id if latest_indicator is not None else None,
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

    # 6. Trade execution via trade intents only.
    if action == "BUY" and not has_open_position:
        intent = TradeIntent(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="BUY",
            confidence=confidence,
            reason_code=reason_code,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expected_exit_price=expected_exit_price,
            metadata={"signal_id": signal.id, "timeframe_policy": details["timeframe_policy"]},
        )
        original_commit = db.commit
        db.commit = db.flush
        try:
            with db.begin_nested():
                trade, snapshot = execute_trade_intent(
                    db,
                    intent=intent,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    fee_amount=Decimal("0.05"),
                )
            logger.info("Auto trader BUY intent executed: trade_id=%s status=%s", trade.id, trade.action)
        except Exception:
            logger.exception("Failed to execute auto trader BUY intent")
        finally:
            db.commit = original_commit

    elif action == "SELL" and has_open_position:
        intent = TradeIntent(
            portfolio_name="gram-paper",
            asset_symbol="XAG_GRAM",
            action="SELL",
            confidence=confidence,
            reason_code=reason_code,
            metadata={"signal_id": signal.id, "timeframe_policy": details["timeframe_policy"]},
        )
        original_commit = db.commit
        db.commit = db.flush
        try:
            with db.begin_nested():
                trade, snapshot = execute_trade_intent(
                    db,
                    intent=intent,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    fee_amount=Decimal("0.05"),
                )
            logger.info("Auto trader SELL intent executed: trade_id=%s status=%s", trade.id, trade.action)
        except Exception:
            logger.exception("Failed to execute auto trader SELL intent")
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
        "strategy_name": active_strategy,
        "indicators": {
            "rsi": float(latest_indicator.rsi_14)
            if (latest_indicator and latest_indicator.rsi_14 is not None)
            else 0.0,
            "sma_20": float(latest_indicator.sma_20)
            if (latest_indicator and latest_indicator.sma_20 is not None)
            else 0.0,
            "sma_50": float(latest_indicator.sma_50)
            if (latest_indicator and latest_indicator.sma_50 is not None)
            else 0.0,
            "bb_upper": float(latest_indicator.bb_upper_20_2)
            if (latest_indicator and latest_indicator.bb_upper_20_2 is not None)
            else 0.0,
            "bb_lower": float(latest_indicator.bb_lower_20_2)
            if (latest_indicator and latest_indicator.bb_lower_20_2 is not None)
            else 0.0,
        },
        "risk_decision": {
            "decision": trade.risk_decision.decision,
            "reason_code": trade.risk_decision.reason_code,
            "risk_level": trade.risk_decision.risk_level,
        }
        if (trade and trade.risk_decision)
        else None,
    }

    if active_strategy == "blended":
        notification_data["regime_info"] = regime_info
        notification_data["strategy_votes"] = strategy_votes
        notification_data["arbiter_decision"] = resolved_stance
        notification_data["arbiter_reason"] = resolution_markdown

    should_notify = True
    if action == "HOLD":
        stmt_prev = select(Signal)
        if signal.id is not None:
            stmt_prev = stmt_prev.where(Signal.id != signal.id)
        stmt_prev = stmt_prev.order_by(Signal.observed_at.desc(), Signal.id.desc()).limit(1)
        prev_signal = db.execute(stmt_prev).scalar_one_or_none()

        if prev_signal and prev_signal.action == "HOLD" and prev_signal.reason_code == reason_code:
            t1 = prev_signal.observed_at
            t2 = signal.observed_at
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=UTC)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=UTC)
            elapsed_time = (t2 - t1).total_seconds()
            if elapsed_time < 6 * 3600:
                should_notify = False

    # Commit transactions
    db.commit()

    # 8. Send Telegram message
    is_silent = notification_data["action"] == "HOLD"
    if should_notify:
        await send_telegram_notification(notification_data, settings, disable_notification=is_silent)


def get_strategy_timeframe_contexts(db: Session, asset_symbol: str) -> dict:
    return {
        timeframe: get_latest_indicator_context(
            db,
            asset_symbol=asset_symbol,
            timeframe=timeframe,
            max_age_minutes=max_age_minutes,
        )
        for timeframe, max_age_minutes in STRATEGY_TIMEFRAME_POLICY.items()
    }


def evaluate_timeframe_guardrails(timeframe_contexts: dict, ref_dt: datetime | None = None) -> list[str]:
    from app.risk.service import is_comex_market_closed

    if ref_dt is None:
        ref_dt = datetime.now(UTC)

    comex_closed = is_comex_market_closed(ref_dt)

    flags: list[str] = []
    daily_readiness = timeframe_contexts["1d"].readiness
    hourly_readiness = timeframe_contexts["1h"].readiness
    execution_readiness = timeframe_contexts["5m"].readiness

    if not daily_readiness.usable or daily_readiness.indicator is None:
        flags.append("DAILY_TREND_MISSING")

    if hourly_readiness.status == "stale":
        if not comex_closed:
            flags.append("ENTRY_TIMEFRAME_STALE")
    elif not hourly_readiness.usable or hourly_readiness.indicator is None:
        flags.append("ENTRY_TIMEFRAME_UNUSABLE")

    if execution_readiness.status == "stale":
        if not comex_closed:
            flags.append("EXECUTION_TIMEFRAME_STALE")
    elif not execution_readiness.usable or execution_readiness.indicator is None:
        flags.append("EXECUTION_TIMEFRAME_UNUSABLE")

    aligned_sources = {
        readiness.source
        for readiness in (
            daily_readiness,
            hourly_readiness,
            execution_readiness,
        )
        if readiness.source is not None
    }
    if len(aligned_sources) > 1:
        flags.append("TIMEFRAME_SOURCE_MISMATCH")

    return flags


def summarize_timeframe_inputs(timeframe_contexts: dict) -> dict:
    summary = {}
    now = datetime.now(UTC)
    for timeframe, context in timeframe_contexts.items():
        readiness = context.readiness
        age_minutes = None
        if readiness.bar_timestamp is not None:
            timestamp = readiness.bar_timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            age_minutes = int((now - timestamp).total_seconds() // 60)
        summary[timeframe] = {
            "usable": readiness.usable,
            "status": readiness.status,
            "source": readiness.source,
            "reason_codes": list(readiness.reason_codes),
            "age_minutes": age_minutes,
            "indicator_id": readiness.indicator_id,
            "bar_timestamp": readiness.bar_timestamp.isoformat() if readiness.bar_timestamp is not None else None,
        }
    return summary
