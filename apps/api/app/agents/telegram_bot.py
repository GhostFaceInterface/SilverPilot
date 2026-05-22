import asyncio
import logging
from decimal import Decimal
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import TelegramError

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Asset, PaperTrade, Portfolio, AgentMemoryEvent, PriceSnapshot
from app.paper_trading.service import calculate_position

logger = logging.getLogger("silverpilot.telegram.bot")


def handle_telegram_command(command: str, db: Session) -> str:
    parts = command.strip().split()
    if not parts:
        return "Lütfen geçerli bir komut girin."
    cmd = parts[0].lower().split("@")[0]

    if cmd == "/durum":
        return get_durum_text(db)
    elif cmd == "/cuzdan":
        return get_cuzdan_text(db)
    elif cmd == "/karzarar":
        return get_karzarar_text(db)
    elif cmd == "/ajanlar":
        return get_ajanlar_text(db)
    elif cmd in ("/start", "/help"):
        return (
            "🤖 *SilverPilot Telegram Portföy & Teşhis Botuna Hoş Geldiniz!*\n\n"
            "Aşağıdaki komutları kullanabilirsiniz:\n"
            "📊 /durum - Gümüş & Portföy bakiyelerini ve dağılımını gösterir.\n"
            "💼 /cuzdan - $600 başlangıç bakiyesine göre cüzdan PNL ve değişim oranını gösterir.\n"
            "📈 /karzarar - Açık pozisyon PNL ve son 5 paper-trade işlemini özetler.\n"
            "🤖 /ajanlar - Son Supreme Arbiter uyuşmazlık ve çözümlenmiş kararları listeler."
        )
    else:
        return f"Bilinmeyen komut: {cmd}\nYardım için /help yazabilirsiniz."


def get_durum_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "default-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG) varlığı bulunamadı."

    position = calculate_position(db, portfolio.id, asset.id)

    snapshot = db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.asset_id == asset.id)
        .order_by(desc(PriceSnapshot.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    mid_price = snapshot.mid_price if snapshot else Decimal("0")

    silver_qty = position.quantity
    silver_value = silver_qty * mid_price
    cash_balance = portfolio.cash_balance
    portfolio_value = cash_balance + silver_value

    ratio = (silver_value / portfolio_value * 100) if portfolio_value > 0 else Decimal("0")
    cash_ratio = Decimal("100") - ratio

    return (
        "📊 *Gümüş & Portföy Durumu*\n\n"
        f"💵 *Nakitteki Bakiye:* {cash_balance:,.2f} USD\n"
        f"🥈 *Gümüş Miktarı:* {silver_qty:,.4f} XAG\n"
        f"💰 *Gümüş Değeri:* {silver_value:,.2f} USD\n"
        f"📈 *Toplam Portföy Değeri:* {portfolio_value:,.2f} USD\n"
        f"⚖️ *Portföy Dağılımı:* %{ratio:.2f} Gümüş / %{cash_ratio:.2f} Nakit"
    )


def get_cuzdan_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "default-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG) varlığı bulunamadı."

    position = calculate_position(db, portfolio.id, asset.id)
    snapshot = db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.asset_id == asset.id)
        .order_by(desc(PriceSnapshot.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    mid_price = snapshot.mid_price if snapshot else Decimal("0")

    silver_qty = position.quantity
    silver_value = silver_qty * mid_price
    cash_balance = portfolio.cash_balance
    portfolio_value = cash_balance + silver_value

    initial_balance = Decimal("600")
    pnl = portfolio_value - initial_balance
    pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else Decimal("0")

    sign = "+" if pnl >= 0 else ""

    return (
        "💼 *Cüzdan Değişim Özeti*\n\n"
        f"💵 *Başlangıç Bakiyesi:* $600.00 USD\n"
        f"📈 *Anlık Portföy Değeri:* ${portfolio_value:,.2f} USD\n"
        f"📊 *Toplam Kar/Zarar (PNL):* {sign}${pnl:,.2f} USD ({sign}{pnl_pct:.2f}%)"
    )


def get_karzarar_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "default-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG) varlığı bulunamadı."

    position = calculate_position(db, portfolio.id, asset.id)
    snapshot = db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.asset_id == asset.id)
        .order_by(desc(PriceSnapshot.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    mid_price = snapshot.mid_price if snapshot else Decimal("0")

    silver_qty = position.quantity
    avg_buy_cost = position.average_buy_cost

    unrealized_pnl = Decimal("0")
    if silver_qty > 0:
        unrealized_pnl = silver_qty * (mid_price - avg_buy_cost)

    sign = "+" if unrealized_pnl >= 0 else ""

    trades = (
        db.execute(
            select(PaperTrade)
            .where(PaperTrade.portfolio_id == portfolio.id)
            .order_by(desc(PaperTrade.created_at))
            .limit(5)
        )
        .scalars()
        .all()
    )

    trades_str = ""
    if trades:
        for idx, trade in enumerate(trades, 1):
            time_str = trade.created_at.strftime("%Y-%m-%d %H:%M")
            action_emoji = (
                "🟢 AL" if trade.action == "paper_buy" else "🔴 SAT" if trade.action == "paper_sell" else "⚪️ BLOKLANDI"
            )
            trades_str += (
                f"{idx}. {action_emoji} | Miktar: {trade.quantity:,.4f} @ {trade.price:,.2f} USD ({time_str})\n"
            )
    else:
        trades_str = "_Henüz bir paper-trade işlemi bulunmuyor._"

    return (
        "📈 *Açık Pozisyon ve Kar/Zarar Durumu*\n\n"
        f"🥈 *Açık Pozisyon:* {silver_qty:,.4f} XAG\n"
        f"🏷️ *Ortalama Alış Maliyeti:* {avg_buy_cost:,.4f} USD/oz\n"
        f"💸 *Anlık Gümüş Fiyatı:* {mid_price:,.4f} USD/oz\n"
        f"📊 *Açık Pozisyon Kar/Zarar:* {sign}${unrealized_pnl:,.2f} USD\n\n"
        f"🔄 *Son 5 Paper Trade İşlemi:*\n{trades_str}"
    )


def get_ajanlar_text(db: Session) -> str:
    disagreements = (
        db.execute(
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.event_type == "agent_disagreement")
            .order_by(desc(AgentMemoryEvent.created_at))
            .limit(3)
        )
        .scalars()
        .all()
    )

    resolutions = (
        db.execute(
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.event_type == "disagreement_resolution")
            .order_by(desc(AgentMemoryEvent.created_at))
            .limit(3)
        )
        .scalars()
        .all()
    )

    lines = ["🤖 *Ajan Teşhis & Supreme Arbiter Kararları*"]

    lines.append("\n🚨 *Son Uyuşmazlıklar (Agent Disagreements):*")
    if disagreements:
        for dis in disagreements:
            val = dis.value_json or {}
            stances = val.get("stances", {})
            stances_str = ", ".join(f"{k}: {v}" for k, v in stances.items())
            time_str = dis.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"• *[{time_str}]* Stances: `{stances_str}`")
            for d in val.get("disagreements", []):
                lines.append(f"  └─ `{d.get('type')}`: {d.get('description')}")
    else:
        lines.append("_Yakın zamanda bir uyuşmazlık tespit edilmedi._")

    lines.append("\n⚖️ *Son Arbiter Kararları (Resolutions):*")
    if resolutions:
        for res in resolutions:
            val = res.value_json or {}
            resolved_stance = val.get("resolved_stance", "NEUTRAL")
            confidence = val.get("confidence", 0.5)
            resolution_markdown = val.get("resolution_markdown", "")
            time_str = res.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"• *[{time_str}]* Karar: *{resolved_stance}* (Güven: {confidence:.2f})")
            short_res = resolution_markdown[:150] + "..." if len(resolution_markdown) > 150 else resolution_markdown
            lines.append(f"  └─ {short_res}")
    else:
        lines.append("_Henüz çözümlenmiş bir arbiter kararı bulunmuyor._")

    return "\n".join(lines)


async def process_telegram_update(update: dict, settings=None):
    if settings is None:
        settings = get_settings()

    if not settings.telegram_bot_token:
        logger.error("Telegram Bot Token is not configured.")
        return

    message = update.get("message")
    if not message:
        message = update.get("edited_message")

    if not message:
        return

    chat = message.get("chat")
    if not chat:
        return

    chat_id = chat.get("id")
    if chat_id != settings.telegram_chat_id:
        logger.warning(f"Unauthorized Telegram Chat ID: {chat_id}. Expected: {settings.telegram_chat_id}")
        return

    text = message.get("text")
    if not text:
        return

    try:
        with SessionLocal() as db:
            reply_text = handle_telegram_command(text, db)
    except Exception as e:
        logger.exception("Database error while processing Telegram command")
        reply_text = f"⚠️ Komut işlenirken bir veritabanı hatası oluştu: {e}"

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(chat_id=settings.telegram_chat_id, text=reply_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}", exc_info=True)


async def set_telegram_webhook():
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram Bot Token is not configured. Webhook will not be set.")
        return

    if not settings.telegram_webhook_url:
        logger.warning("Telegram Webhook URL is not configured. Webhook registration skipped.")
        return

    bot = Bot(token=settings.telegram_bot_token)
    webhook_url = f"{settings.telegram_webhook_url.rstrip('/')}/agent/telegram/webhook"
    logger.info(f"Setting Telegram webhook to: {webhook_url}")

    try:
        await bot.set_webhook(url=webhook_url)
        logger.info("Telegram webhook successfully registered.")
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}", exc_info=True)


async def start_polling():
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram Bot Token is not configured. Polling will not start.")
        return

    bot = Bot(token=settings.telegram_bot_token)
    logger.info("Starting Telegram bot polling task in background...")

    offset = 0
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=10)
            for update in updates:
                offset = update.update_id + 1
                await process_telegram_update(update.to_dict(), settings)
        except asyncio.CancelledError:
            logger.info("Telegram polling task cancelled.")
            break
        except TelegramError as e:
            logger.error(f"Telegram error in polling loop: {e}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error in polling: {e}", exc_info=True)
            await asyncio.sleep(5)
