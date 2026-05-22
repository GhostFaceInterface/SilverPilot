import logging
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import Bot

from app.core.config import get_settings
from app.models import Asset, PriceSnapshot, TechnicalIndicator, Portfolio, Signal, PaperTrade
from app.services.strategy import StrategyRunner
from app.paper_trading.service import execute_paper_trade, calculate_position
from app.schemas.paper_trading import PaperTradeRequest

logger = logging.getLogger("silverpilot.services.auto_trader")

async def send_telegram_notification(trade_data: dict, settings):
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
    else:
        # Unknown action or holds
        return

    # Construct Markdown message
    risk_info = ""
    risk_decision = trade_data.get("risk_decision")
    if risk_decision:
        risk_info = (
            f"\n⚖️ *Risk Kararı:* {risk_decision['decision'].upper()}\n"
            f"🔍 *Neden Kodu:* `{risk_decision['reason_code']}`\n"
            f"📊 *Risk Seviyesi:* {risk_decision['risk_level']}\n"
        )

    msg = (
        f"{status_emoji} *SilverPilot Auto-Trading Raporu*\n\n"
        f"🔄 *İşlem Tipi:* {action_str}\n"
        f"🥈 *Varlık:* XAG (Gümüş)\n"
        f"🏷️ *İşlem Fiyatı:* {trade_data['price']:,.4f} USD/oz\n"
        f"📦 *Miktar:* {trade_data['quantity']:,.4f} XAG\n"
        f"💰 *Net Tutar:* {trade_data['net_amount']:,.2f} USD\n"
        f"💸 *Komisyon (Fees):* {trade_data['fees']:,.2f} USD\n"
        f"💵 *Yeni Nakit Bakiyesi:* {trade_data['cash_balance']:,.2f} USD\n"
        f"{risk_info}"
    )

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=msg,
            parse_mode="Markdown"
        )
        logger.info("Telegram notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)


async def run_auto_trading(db: Session = None):
    logger.info("Starting run_auto_trading evaluation...")
    settings = get_settings()

    if not settings.auto_trading_enabled:
        logger.info("Auto trading is disabled in settings.")
        return

    if db is not None:
        # Explicit session provided (e.g. from unit tests)
        await _run_auto_trading_impl(db, settings)
    else:
        # Isolated connection block for background production threads/tasks
        from app.core.db import SessionLocal
        db_session = SessionLocal()
        try:
            await _run_auto_trading_impl(db_session, settings)
        except Exception as e:
            logger.error(f"Auto trading loop encountered a fatal exception: {e}", exc_info=True)
        finally:
            db_session.close()


async def _run_auto_trading_impl(db: Session, settings):
    # 1. Fetch portfolio 'default-paper'
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "default-paper")).scalar_one_or_none()
    if not portfolio:
        logger.error("Portfolio 'default-paper' not found")
        return

    # 2. Fetch asset 'XAG'
    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one_or_none()
    if not asset:
        logger.error("Asset 'XAG' not found")
        return

    # 3. Fetch two latest indicators from source 'yahoo-si-f'
    stmt = (
        select(TechnicalIndicator)
        .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
        .where(PriceSnapshot.source == "yahoo-si-f")
        .order_by(TechnicalIndicator.bar_timestamp.desc())
        .limit(2)
    )
    indicators = db.execute(stmt).scalars().all()
    if not indicators:
        logger.warning("No technical indicators found for source yahoo-si-f")
        return

    latest_indicator = indicators[0]
    prev_indicator = indicators[1] if len(indicators) > 1 else None

    # Get matching PriceSnapshot for the latest indicator
    latest_snapshot = latest_indicator.price_snapshot
    if not latest_snapshot:
        latest_snapshot = db.execute(select(PriceSnapshot).where(PriceSnapshot.id == latest_indicator.price_snapshot_id)).scalar_one_or_none()

    if not latest_snapshot:
        logger.error(f"PriceSnapshot not found for indicator ID {latest_indicator.id}")
        return

    # Get position status
    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0

    # 4. Evaluate strategy
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
    signal = Signal(
        observed_at=latest_snapshot.observed_at,
        price_snapshot_id=latest_snapshot.id,
        indicator_id=latest_indicator.id,
        action=action,
        reason_code=reason_code,
        price_usd_oz=latest_snapshot.mid_price,
        details_json={
            "strategy_name": settings.strategy_name,
            "rsi_14": float(latest_indicator.rsi_14) if latest_indicator.rsi_14 is not None else None,
            "sma_20": float(latest_indicator.sma_20) if latest_indicator.sma_20 is not None else None,
            "sma_50": float(latest_indicator.sma_50) if latest_indicator.sma_50 is not None else None,
            "bb_lower": float(latest_indicator.bb_lower_20_2) if latest_indicator.bb_lower_20_2 is not None else None,
            "bb_upper": float(latest_indicator.bb_upper_20_2) if latest_indicator.bb_upper_20_2 is not None else None,
        }
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
                portfolio_name="default-paper",
                asset_symbol="XAG",
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
            except Exception as e:
                db.rollback()
                logger.exception("Failed to execute auto trader BUY")
        else:
            logger.warning(f"Insufficient cash balance to buy: {cash}")

    elif action == "SELL" and has_open_position:
        request = PaperTradeRequest(
            portfolio_name="default-paper",
            asset_symbol="XAG",
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
        except Exception as e:
            db.rollback()
            logger.exception("Failed to execute auto trader SELL")

    # 7. Extract notification data prior to commit/close to avoid DetachedInstanceError
    notification_data = None
    if trade is not None and trade.action in ("paper_buy", "paper_sell", "blocked"):
        notification_data = {
            "action": trade.action,
            "price": float(trade.price),
            "quantity": float(trade.quantity),
            "net_amount": float(trade.net_amount),
            "fees": float(trade.fees),
            "cash_balance": float(portfolio.cash_balance),
            "risk_decision": {
                "decision": trade.risk_decision.decision,
                "reason_code": trade.risk_decision.reason_code,
                "risk_level": trade.risk_decision.risk_level,
            } if trade.risk_decision else None
        }

    # Commit transactions
    db.commit()

    # 8. Send Telegram message if trade was executed or blocked
    if notification_data is not None:
        await send_telegram_notification(notification_data, settings)

