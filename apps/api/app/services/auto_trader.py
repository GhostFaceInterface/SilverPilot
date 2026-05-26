import logging
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Bot

from app.core.config import get_settings
from app.models import Asset, PriceSnapshot, TechnicalIndicator, Portfolio, Signal
from app.services.strategy import StrategyRunner
from app.paper_trading.service import execute_paper_trade, calculate_position
from app.schemas.paper_trading import PaperTradeRequest
from app.services.regime import get_market_regime
from app.agents.orchestrator import run_blended_consensus_resolution

logger = logging.getLogger("silverpilot.services.auto_trader")


def sanitize_markdown(text: str) -> str:
    """Escapes markdown control characters and converts ** to * for Telegram Markdown V1."""
    if not text:
        return ""
    # Convert standard double-asterisk bold (**) to Markdown V1 single-asterisk bold (*)
    text = text.replace("**", "*")
    # Escape underscores to prevent them from starting italic blocks
    text = text.replace("\\_", "_").replace("_", "\\_")
    # Escape brackets to prevent unmatched link structures
    text = text.replace("\\[", "[").replace("[", "\\[")
    text = text.replace("\\]", "]").replace("]", "\\]")
    return text


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
            reason_safe = reason.replace("_", " ") if reason else ""
            emoji = "🟢 AL" if act == "BUY" else ("🔴 SAT" if act == "SELL" else "⚪️ BEKLE")
            return f"{emoji} ({reason_safe})" if reason_safe else emoji

        rsi_vote = format_vote(votes.get("rsi"))
        bb_vote = format_vote(votes.get("bollinger"))
        sma_vote = format_vote(votes.get("sma_cross"))

        arbiter_stance = trade_data.get("arbiter_decision", "NEUTRAL")
        arbiter_emoji = (
            "🟢 AL" if arbiter_stance == "BULLISH" else ("🔴 SAT" if arbiter_stance == "BEARISH" else "⚪️ BEKLE")
        )
        arbiter_reason = sanitize_markdown(trade_data.get("arbiter_reason", "Gerekçe belirtilmedi."))

        msg = (
            f"📊 *SilverPilot Canlı Analiz Raporu*\n\n"
            f"🥈 *Gümüş (XAG\\_GRAM):* {trade_data['price']:,.4f} USD/gram\n"
            f"📈 *Piyasa Rejimi:* {regime_label}\n\n"
            f"🗳️ *Strateji Oylaması:*\n"
            f"• RSI (14): {rsi_vote}\n"
            f"• Bollinger Bands: {bb_vote}\n"
            f"• SMA Cross (20/50): {sma_vote}\n\n"
            f"👑 *Yüce Hakem Kararı:* {arbiter_emoji}\n"
            f"📝 *Gerekçe:* {arbiter_reason}\n\n"
            f"🔄 *İşlem Durumu:* {status_emoji} {action_str}\n"
        )

        if action in ("paper_buy", "paper_sell"):
            msg += (
                f"📦 *Miktar:* {trade_data.get('quantity', 0.0):,.4f} XAG\\_GRAM\n"
                f"💰 *Net Tutar:* {trade_data.get('net_amount', 0.0):,.2f} USD\n"
            )

        msg += f"💵 *Nakit Bakiyesi:* {trade_data.get('cash_balance', 0.0):,.2f} USD\n"
        if "xag_balance" in trade_data:
            msg += f"🥈 *Gümüş Portföyü:* {trade_data['xag_balance']:,.4f} XAG\\_GRAM\n"

        risk_decision = trade_data.get("risk_decision")
        if risk_decision:
            msg += (
                f"\n⚖️ *Risk Kararı:* {risk_decision['decision'].upper()}\n"
                f"🔍 *Neden Kodu:* `{risk_decision['reason_code']}`\n"
                f"📊 *Risk Seviyesi:* {risk_decision['risk_level']}\n"
            )
    else:
        risk_info = ""
        risk_decision = trade_data.get("risk_decision")
        if risk_decision:
            risk_info = (
                f"\n⚖️ *Risk Kararı:* {risk_decision['decision'].upper()}\n"
                f"🔍 *Neden Kodu:* `{risk_decision['reason_code']}`\n"
                f"📊 *Risk Seviyesi:* {risk_decision['risk_level']}\n"
            )

        indicator_details = ""
        indicators = trade_data.get("indicators", {})
        if indicators:
            indicator_details = (
                f"\n📊 *Teknik Göstergeler:*\n"
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
            regime_details = f"📈 *Piyasa Rejimi:* {regime_label}\n"

        msg = (
            f"{status_emoji} *SilverPilot Auto-Trading Raporu*\n\n"
            f"🔄 *İşlem Tipi:* {action_str}\n"
            f"🥈 *Varlık:* XAG_GRAM (Gümüş)\n"
            f"🏷️ *Fiyat:* {trade_data['price']:,.4f} USD/gram\n"
            f"{regime_details}"
        )
        if action in ("paper_buy", "paper_sell", "blocked"):
            msg += (
                f"📦 *Miktar:* {trade_data.get('quantity', 0.0):,.4f} XAG_GRAM\n"
                f"💰 *Net Tutar:* {trade_data.get('net_amount', 0.0):,.2f} USD\n"
                f"💸 *Komisyon (Fees):* {trade_data.get('fees', 0.0):,.2f} USD\n"
            )
        msg += f"💵 *Nakit Bakiyesi:* {trade_data.get('cash_balance', 0.0):,.2f} USD\n"
        msg += f"{indicator_details}{risk_info}"

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=msg,
            parse_mode="Markdown",
            disable_notification=disable_notification,
        )
        logger.info(f"Telegram notification sent successfully (silent={disable_notification}).")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)


async def run_auto_trading(db: Session = None):
    logger.info("Starting run_auto_trading evaluation...")
    settings = get_settings()

    if not settings.auto_trading_enabled:
        logger.info("Auto trading is disabled in settings.")
        return

    if db is not None:
        await _run_auto_trading_impl(db, settings)
    else:
        from app.core.db import SessionLocal

        db_session = SessionLocal()
        try:
            await _run_auto_trading_impl(db_session, settings)
        except Exception as e:
            logger.error(f"Auto trading loop encountered a fatal exception: {e}", exc_info=True)
        finally:
            db_session.close()


async def _run_auto_trading_impl(db: Session, settings):
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
            PriceSnapshot.asset_id == asset.id
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
            try:
                trade, snapshot = execute_paper_trade(db, request)
                logger.info(f"Auto trader BUY executed: trade_id={trade.id}, status={trade.action}")
            except Exception:
                db.rollback()
                logger.exception("Failed to execute auto trader BUY")
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
        try:
            trade, snapshot = execute_paper_trade(db, request)
            logger.info(f"Auto trader SELL executed: trade_id={trade.id}, status={trade.action}")
        except Exception:
            db.rollback()
            logger.exception("Failed to execute auto trader SELL")

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
