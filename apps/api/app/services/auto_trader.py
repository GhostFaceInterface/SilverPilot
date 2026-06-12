import logging
import html
import re
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Portfolio, Signal, AgentMemoryEvent
from app.services.strategy import StrategyRunner, STRATEGY_REGISTRY
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
    ACTION_MAP = {
        "BUY": ("ALIM ADAYI (BUY)", "🟢"),
        "SELL": ("SATIM ADAYI (SELL)", "🔴"),
        "paper_buy": ("ALIM (BUY)", "🟢"),
        "paper_sell": ("SATIM (SELL)", "🔴"),
        "blocked": ("ENGELLENDİ (BLOCKED)", "⚠️"),
        "HOLD": ("BEKLE (HOLD)", "⚪️"),
    }
    action = trade_data["action"]
    if action not in ACTION_MAP:
        return
    action_str, status_emoji = ACTION_MAP[action]

    is_blended = trade_data.get("strategy_name") == "blended"

    if is_blended:
        regime_info = trade_data.get("regime_info", {})
        regime_label = "Yatay Sakin Piyasa (SIDEWAYS)"
        REGIME_MAP = {
            "TRENDING_UP": "Güçlü Yükseliş Trendi (TRENDING UP)",
            "TRENDING_DOWN": "Güçlü Düşüş Trendi (TRENDING DOWN)",
        }
        regime = regime_info.get("regime", "SIDEWAYS")
        regime_label = REGIME_MAP.get(regime, "Yatay Sakin Piyasa (SIDEWAYS)")

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
            REGIME_MAP = {
                "TRENDING_UP": "Güçlü Yükseliş Trendi (TRENDING UP)",
                "TRENDING_DOWN": "Güçlü Düşüş Trendi (TRENDING DOWN)",
            }
            regime = regime_info.get("regime", "SIDEWAYS")
            regime_label = REGIME_MAP.get(regime, "Yatay Sakin Piyasa (SIDEWAYS)")
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
    requested_strategy = settings.strategy_name or "strategy_v2"
    active_strategy = requested_strategy
    action = "HOLD"
    candidate_action = "HOLD"
    reason_code = "UNKNOWN"
    confidence = Decimal("0.5000")
    stop_loss_price = None
    take_profit_price = None
    expected_exit_price = None
    details = {}

    has_block_flag = False
    block_reason = None
    prioritized_block_flags = [
        "TIMEFRAME_SOURCE_MISMATCH",
        "ENTRY_TIMEFRAME_STALE",
        "ENTRY_TIMEFRAME_UNUSABLE",
        "DAILY_TREND_MISSING",
        "EXECUTION_TIMEFRAME_STALE",
        "EXECUTION_TIMEFRAME_UNUSABLE",
    ]
    block_reason = next((flag for flag in prioritized_block_flags if flag in strategy_readiness_flags), None)
    has_block_flag = block_reason is not None

    invalid_strategy = active_strategy not in STRATEGY_REGISTRY

    if invalid_strategy:
        action = "HOLD"
        reason_code = "BLOCKED_CONFIG_INVALID"
        confidence = Decimal("0.9900")
        details = {
            "strategy_name": active_strategy,
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            "readiness_block_flags": strategy_readiness_flags,
            "config_error": f"Strategy {active_strategy} not registered in STRATEGY_REGISTRY",
        }
    elif has_block_flag:
        action = "HOLD"
        reason_code = block_reason
        confidence_map = {
            "TIMEFRAME_SOURCE_MISMATCH": Decimal("0.9900"),
            "ENTRY_TIMEFRAME_STALE": Decimal("0.9800"),
            "ENTRY_TIMEFRAME_UNUSABLE": Decimal("0.9800"),
            "DAILY_TREND_MISSING": Decimal("0.9900"),
        }
        confidence = confidence_map.get(block_reason, Decimal("0.9700"))

        details = {
            "strategy_name": active_strategy,
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            "readiness_block_flags": strategy_readiness_flags,
        }
    else:
        # Resolve strategy from STRATEGY_REGISTRY
        strategy = STRATEGY_REGISTRY[active_strategy]

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

        macd_line = latest_indicator.macd_line if latest_indicator else None
        macd_signal = latest_indicator.macd_signal if latest_indicator else None
        prev_macd_line = (
            hourly_context.previous_indicator.macd_line
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )
        prev_macd_signal = (
            hourly_context.previous_indicator.macd_signal
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        )

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

        context = {
            "close": close,
            "rsi_14": rsi_14,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "prev_sma_20": prev_sma_20,
            "prev_sma_50": prev_sma_50,
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "prev_macd_line": prev_macd_line,
            "prev_macd_signal": prev_macd_signal,
            "atr_value": atr_value,
            "close_value": close_value,
            "has_open_position": has_open_position,
            "asset": asset,
            "hourly_context": hourly_context,
            "daily_context": daily_context,
            "latest_indicator": latest_indicator,
            "latest_snapshot": latest_snapshot,
            "latest_event": latest_event,
            "readiness_block_flags": strategy_readiness_flags,
        }

        strategy_decision = await strategy.evaluate(db, context)

        action = strategy_decision.action
        reason_code = strategy_decision.reason_code
        confidence = strategy_decision.confidence
        stop_loss_price = strategy_decision.stop_loss_price
        take_profit_price = strategy_decision.take_profit_price
        expected_exit_price = strategy_decision.expected_exit_price

        details = {
            "strategy_name": active_strategy,
            "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"},
            "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
            "agent_sentiment": news_sentiment,
            **strategy_decision.to_signal_details(),
        }
        if strategy_decision.exit_metadata:
            details.update(strategy_decision.exit_metadata)

    logger.info("Strategy %s evaluation: action=%s reason=%s.", active_strategy, action, reason_code)
    candidate_action = action

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
    decision_envelope = build_decision_envelope(
        mode=settings.auto_trading_mode,
        asset_symbol=asset.symbol,
        requested_strategy=requested_strategy,
        resolved_strategy=active_strategy if not invalid_strategy else None,
        candidate_action=candidate_action,
        final_action=action,
        reason_code=reason_code,
        timeframe_contexts=timeframe_contexts,
        readiness_block_flags=strategy_readiness_flags,
        filter_reason=filter_reason,
        execution={
            "status": "pending",
            "skipped_reason": None,
            "trade_id": None,
        },
        notification={
            "sent": False,
            "skipped_reason": "pending",
            "cooldown_seconds": settings.hold_notification_cooldown_minutes * 60,
        },
    )
    if invalid_strategy:
        decision_envelope["execution"] = {
            "status": "skipped",
            "skipped_reason": "config_invalid",
            "trade_id": None,
        }

    signal = Signal(
        observed_at=latest_snapshot.observed_at,
        price_snapshot_id=latest_snapshot.id,
        indicator_id=latest_indicator.id if latest_indicator is not None else None,
        action=action,
        reason_code=reason_code,
        price_usd_oz=latest_snapshot.mid_price,
        details_json={**details, "decision_envelope": decision_envelope},
    )
    db.add(signal)
    db.flush()

    trade = None
    buy_price = latest_snapshot.buy_price if latest_snapshot.buy_price else latest_snapshot.mid_price
    sell_price = latest_snapshot.sell_price if latest_snapshot.sell_price else latest_snapshot.mid_price

    execution_result = decision_envelope["execution"]

    # 6. Trade execution via trade intents only.
    if settings.auto_trading_mode == "diagnostic":
        execution_result = {
            "status": "skipped",
            "skipped_reason": "diagnostic_mode",
            "trade_id": None,
        }
    elif action == "BUY" and not has_open_position:
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
            execution_result = {
                "status": "executed" if trade.action == "paper_buy" else "blocked",
                "skipped_reason": None if trade.action == "paper_buy" else trade.risk_decision.reason_code,
                "trade_id": trade.id,
            }
        except Exception:
            logger.exception("Failed to execute auto trader BUY intent")
            execution_result = {"status": "failed", "skipped_reason": "execution_exception", "trade_id": None}
        finally:
            db.commit = original_commit

    elif settings.auto_trading_mode == "paper" and action == "SELL" and has_open_position:
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
            execution_result = {
                "status": "executed" if trade.action == "paper_sell" else "blocked",
                "skipped_reason": None if trade.action == "paper_sell" else trade.risk_decision.reason_code,
                "trade_id": trade.id,
            }
        except Exception:
            logger.exception("Failed to execute auto trader SELL intent")
            execution_result = {"status": "failed", "skipped_reason": "execution_exception", "trade_id": None}
        finally:
            db.commit = original_commit
    else:
        skipped_reason = "not_actionable"
        if action == "BUY" and has_open_position:
            skipped_reason = "position_already_open"
        elif action == "SELL" and not has_open_position:
            skipped_reason = "no_open_position"
        elif reason_code == "BLOCKED_CONFIG_INVALID":
            skipped_reason = "config_invalid"
        execution_result = {"status": "skipped", "skipped_reason": skipped_reason, "trade_id": None}

    # 7. Extract notification data prior to commit/close to avoid DetachedInstanceError
    notification_data = {
        "action": trade.action if trade else ("blocked" if reason_code.startswith("BLOCKED_") else action),
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
        meta = strategy_decision.exit_metadata or {}
        notification_data["regime_info"] = meta.get("regime_info")
        notification_data["strategy_votes"] = meta.get("strategy_votes")
        notification_data["arbiter_decision"] = meta.get("arbiter_decision")
        notification_data["arbiter_reason"] = meta.get("arbiter_reason")

    notification_decision = should_send_trade_notification(
        db,
        signal=signal,
        asset_symbol=asset.symbol,
        strategy_name=active_strategy,
        notification_action=notification_data["action"],
        cooldown_minutes=settings.hold_notification_cooldown_minutes,
    )
    should_notify = notification_decision["sent"]

    refreshed_details = dict(signal.details_json or {})
    refreshed_envelope = dict(refreshed_details.get("decision_envelope") or {})
    refreshed_envelope["execution"] = execution_result
    refreshed_envelope["notification"] = notification_decision
    if trade and trade.risk_decision:
        refreshed_envelope["risk_preflight"] = {
            "decision": trade.risk_decision.decision,
            "reason_code": trade.risk_decision.reason_code,
            "risk_level": trade.risk_decision.risk_level,
        }
    refreshed_details["decision_envelope"] = refreshed_envelope
    signal.details_json = refreshed_details

    # Commit transactions
    db.commit()

    # 8. Send Telegram message
    is_silent = notification_data["action"] == "HOLD"
    if should_notify:
        await send_telegram_notification(notification_data, settings, disable_notification=is_silent)


def build_decision_envelope(
    *,
    mode: str,
    asset_symbol: str,
    requested_strategy: str,
    resolved_strategy: str | None,
    candidate_action: str,
    final_action: str,
    reason_code: str,
    timeframe_contexts: dict,
    readiness_block_flags: list[str],
    filter_reason: str | None,
    execution: dict,
    notification: dict,
) -> dict:
    return {
        "schema_version": 1,
        "mode": mode,
        "asset_symbol": asset_symbol,
        "requested_strategy": requested_strategy,
        "resolved_strategy": resolved_strategy,
        "candidate_action": candidate_action,
        "final_action": final_action,
        "reason_code": reason_code,
        "readiness": {
            "block_flags": list(readiness_block_flags),
            "timeframes": summarize_timeframe_inputs(timeframe_contexts),
        },
        "risk_preflight": {"decision": "not_evaluated", "reason_code": None, "risk_level": None},
        "agent_filter": {
            "applied": filter_reason is not None,
            "reason_code": filter_reason,
        },
        "execution": execution,
        "notification": notification,
    }


def should_send_trade_notification(
    db: Session,
    *,
    signal: Signal,
    asset_symbol: str,
    strategy_name: str,
    notification_action: str,
    cooldown_minutes: int,
) -> dict:
    cooldown_seconds = cooldown_minutes * 60
    if notification_action != "HOLD" or cooldown_seconds <= 0:
        return {"sent": True, "skipped_reason": None, "cooldown_seconds": cooldown_seconds}

    stmt_prev = select(Signal).where(Signal.action == "HOLD", Signal.reason_code == signal.reason_code)
    if signal.id is not None:
        stmt_prev = stmt_prev.where(Signal.id != signal.id)
    stmt_prev = stmt_prev.order_by(Signal.observed_at.desc(), Signal.id.desc()).limit(25)
    previous_signals = db.execute(stmt_prev).scalars().all()

    current_time = signal.observed_at
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    for prev_signal in previous_signals:
        details = prev_signal.details_json or {}
        envelope = details.get("decision_envelope") or {}
        if envelope:
            if envelope.get("asset_symbol") != asset_symbol or envelope.get("resolved_strategy") != strategy_name:
                continue
        elif details.get("strategy_name") != strategy_name:
            continue

        previous_time = prev_signal.observed_at
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=UTC)
        if (current_time - previous_time).total_seconds() < cooldown_seconds:
            return {
                "sent": False,
                "skipped_reason": "hold_cooldown",
                "cooldown_seconds": cooldown_seconds,
            }

    return {"sent": True, "skipped_reason": None, "cooldown_seconds": cooldown_seconds}


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

    if hourly_readiness.status == "stale" and not comex_closed:
        flags.append("ENTRY_TIMEFRAME_STALE")
    elif not hourly_readiness.usable or hourly_readiness.indicator is None:
        flags.append("ENTRY_TIMEFRAME_UNUSABLE")

    if execution_readiness.status == "stale" and not comex_closed:
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
