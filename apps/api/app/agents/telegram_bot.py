import asyncio
import logging
import io
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import TelegramError

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Asset, PaperTrade, Portfolio, AgentMemoryEvent, PriceSnapshot
from app.paper_trading.service import calculate_position

logger = logging.getLogger("silverpilot.telegram.bot")


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
            "💼 /cuzdan - $2,500 başlangıç bakiyesine göre cüzdan PNL ve değişim oranını gösterir.\n"
            "📈 /karzarar - Açık pozisyon PNL ve son 5 paper-trade işlemini özetler.\n"
            "🤖 /ajanlar - Son Supreme Arbiter uyuşmazlık ve çözümlenmiş kararları listeler."
        )
    else:
        return f"Bilinmeyen komut: {cmd}\nYardım için /help yazabilirsiniz."


def get_durum_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG_GRAM) varlığı bulunamadı."

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
        "📊 *Gümüş & Portföy Durumu (Gram/USD)*\n\n"
        f"💵 *Nakitteki Bakiye:* {cash_balance:,.2f} USD\n"
        f"🥈 *Gümüş Miktarı:* {silver_qty:,.6f} gram\n"
        f"💰 *Gümüş Değeri:* {silver_value:,.2f} USD\n"
        f"📈 *Toplam Portföy Değeri:* {portfolio_value:,.2f} USD\n"
        f"⚖️ *Portföy Dağılımı:* %{ratio:.2f} Gümüş / %{cash_ratio:.2f} Nakit"
    )


def get_cuzdan_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG_GRAM) varlığı bulunamadı."

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

    initial_balance = portfolio.initial_cash
    pnl = portfolio_value - initial_balance
    pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else Decimal("0")

    sign = "+" if pnl >= 0 else ""

    return (
        "💼 *Cüzdan Değişim Özeti (Gram/USD)*\n\n"
        f"💵 *Başlangıç Bakiyesi:* ${initial_balance:,.2f} USD\n"
        f"📈 *Anlık Portföy Değeri:* ${portfolio_value:,.2f} USD\n"
        f"📊 *Toplam Kar/Zarar (PNL):* {sign}${pnl:,.2f} USD ({sign}{pnl_pct:.2f}%)"
    )


def get_karzarar_text(db: Session) -> str:
    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    if not portfolio:
        portfolio = db.execute(select(Portfolio).order_by(Portfolio.created_at)).scalars().first()
    if not portfolio:
        return "❌ Aktif portföy bulunamadı."

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG_GRAM) varlığı bulunamadı."

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
                f"{idx}. {action_emoji} | Miktar: {trade.quantity:,.6f} gram @ {trade.price:,.6f} USD/gram ({time_str})\n"
            )
    else:
        trades_str = "_Henüz bir paper-trade işlemi bulunmuyor._"

    return (
        "📈 *Açık Pozisyon ve Kar/Zarar Durumu (Gram/USD)*\n\n"
        f"🥈 *Açık Pozisyon:* {silver_qty:,.6f} gram\n"
        f"🏷️ *Ortalama Alış Maliyeti:* {avg_buy_cost:,.6f} USD/gram\n"
        f"💸 *Anlık Gümüş Fiyatı:* {mid_price:,.6f} USD/gram\n"
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
            .where(AgentMemoryEvent.event_type.in_(["disagreement_resolution", "blended_consensus_resolution"]))
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
                desc_safe = sanitize_markdown(d.get("description", ""))
                lines.append(f"  └─ `{d.get('type')}`: {desc_safe}")
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
            short_res_safe = sanitize_markdown(short_res)
            lines.append(f"  └─ {short_res_safe}")
    else:
        lines.append("_Henüz çözümlenmiş bir arbiter kararı bulunmuyor._")

    return "\n".join(lines)


def generate_daily_price_chart(db: Session) -> io.BytesIO | None:
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)
    
    # Try kuveyt first
    stmt = select(PriceSnapshot).where(
        PriceSnapshot.source == "kuveyt-public-silver-page",
        PriceSnapshot.observed_at >= twenty_four_hours_ago
    ).order_by(PriceSnapshot.observed_at.asc())
    snapshots = db.execute(stmt).scalars().all()
    
    if not snapshots:
        stmt = select(PriceSnapshot).where(
            PriceSnapshot.source == "yahoo-si-f",
            PriceSnapshot.observed_at >= twenty_four_hours_ago
        ).order_by(PriceSnapshot.observed_at.asc())
        snapshots = db.execute(stmt).scalars().all()
        
    if not snapshots:
        return None
        
    tr_tz = timezone(timedelta(hours=3))
    times = [s.observed_at.astimezone(tr_tz) for s in snapshots]
    prices = [float(s.mid_price) for s in snapshots]
    
    min_time = min(times)
    max_time = max(times)
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=150)
    fig.patch.set_facecolor('#121212')
    ax.set_facecolor('#1e1e1e')
    
    # Plot line
    ax.plot(times, prices, color='#00e5ff', linewidth=2.5, label='Gümüş (XAG/USD) Orta Fiyat')
    
    # Draw boundary spans
    boundaries = []
    start_day = (min_time - timedelta(days=1)).date()
    end_day = (max_time + timedelta(days=1)).date()
    curr_day = start_day
    while curr_day <= end_day:
        for hour in [0, 8, 16]:
            dt = datetime.combine(curr_day, datetime.min.time(), tzinfo=tr_tz) + timedelta(hours=hour)
            boundaries.append(dt)
        curr_day += timedelta(days=1)
    
    boundaries.sort()
    
    y_min, y_max = min(prices), max(prices)
    y_range = y_max - y_min if y_max > y_min else 1.0
    ax.set_ylim(y_min - y_range * 0.15, y_max + y_range * 0.25)
    
    label_y = y_max + y_range * 0.15
    
    # Shade spans
    for i in range(len(boundaries) - 1):
        b1 = boundaries[i]
        b2 = boundaries[i+1]
        
        # Intersection
        i_start = max(b1, min_time)
        i_end = min(b2, max_time)
        
        if i_start >= i_end:
            continue
            
        # Determine session
        if b1.hour == 0:
            color = '#007acc'
            label = "Sabah Seansı\n(00:00 - 08:00)"
            alpha = 0.08
        elif b1.hour == 8:
            color = '#d4af37'
            label = "Öğle-Avrupa Seansı\n(08:00 - 16:00)"
            alpha = 0.08
        else:
            color = '#8a2be2'
            label = "Akşam-Amerika Seansı\n(16:00 - 24:00)"
            alpha = 0.08
            
        ax.axvspan(i_start, i_end, color=color, alpha=alpha)
        
        # Place label if the span is wide enough (at least 2 hours)
        span_hours = (i_end - i_start).total_seconds() / 3600.0
        if span_hours >= 2.0:
            mid_x = i_start + (i_end - i_start) / 2
            ax.text(mid_x, label_y, label, color=color, ha='center', va='top', fontsize=8.5, weight='bold')

    # Formatting axes
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=tr_tz))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    
    ax.tick_params(colors='#888888', labelsize=9)
    ax.grid(True, color='#2d2d2d', linestyle='--', linewidth=0.5)
    
    # Labels and titles
    ax.set_title('🥈 SilverPilot Gümüş (XAG) Günlük Fiyat Değişim Analizi 📊', color='#ffffff', fontsize=13, weight='bold', pad=25)
    ax.set_ylabel('Fiyat (USD/oz)', color='#888888', fontsize=10, labelpad=10)
    
    # Style border
    for spine in ax.spines.values():
        spine.set_color('#2d2d2d')
        
    # Legend
    legend = ax.legend(loc='lower right', facecolor='#1e1e1e', edgecolor='#2d2d2d')
    for text in legend.get_texts():
        text.set_color('#ffffff')
        
    plt.tight_layout()
    
    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_daily_price_caption(db: Session) -> str:
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)
    
    stmt = select(PriceSnapshot).where(
        PriceSnapshot.source == "kuveyt-public-silver-page",
        PriceSnapshot.observed_at >= twenty_four_hours_ago
    ).order_by(PriceSnapshot.observed_at.asc())
    snapshots = db.execute(stmt).scalars().all()
    
    if not snapshots:
        stmt = select(PriceSnapshot).where(
            PriceSnapshot.source == "yahoo-si-f",
            PriceSnapshot.observed_at >= twenty_four_hours_ago
        ).order_by(PriceSnapshot.observed_at.asc())
        snapshots = db.execute(stmt).scalars().all()
        
    if not snapshots:
        return "📊 *Seanslık Fiyat Analiz Özeti*\nVeri bulunamadı."
        
    tr_tz = timezone(timedelta(hours=3))
    
    sabah_prices = []
    ogle_prices = []
    aksam_prices = []
    all_prices = []
    
    for s in snapshots:
        local_dt = s.observed_at.astimezone(tr_tz)
        price = float(s.mid_price)
        all_prices.append(price)
        
        if 0 <= local_dt.hour < 8:
            sabah_prices.append(price)
        elif 8 <= local_dt.hour < 16:
            ogle_prices.append(price)
        else:
            aksam_prices.append(price)
            
    # Calculate stats
    def get_stats(lst):
        if not lst:
            return "Veri Yok"
        return f"Min: {min(lst):.3f} | Max: {max(lst):.3f} | Ort: {sum(lst)/len(lst):.3f}"
        
    sabah_str = get_stats(sabah_prices)
    ogle_str = get_stats(ogle_prices)
    aksam_str = get_stats(aksam_prices)
    
    overall_min = min(all_prices)
    overall_max = max(all_prices)
    latest_price = all_prices[-1]
    
    # Calculate daily change
    daily_change = latest_price - all_prices[0]
    daily_change_pct = (daily_change / all_prices[0] * 100) if all_prices[0] > 0 else 0.0
    sign = "+" if daily_change >= 0 else ""
    
    caption = (
        "📊 *SilverPilot Günlük Seans & Fiyat Raporu*\n\n"
        f"🥈 *Son Fiyat (Canlı):* {latest_price:.4f} USD/oz\n"
        f"📈 *Günlük Değişim:* {sign}{daily_change:.4f} USD ({sign}{daily_change_pct:.2f}%)\n"
        f"⚖️ *Günlük Aralık:* {overall_min:.4f} - {overall_max:.4f} USD/oz\n\n"
        "🕰️ *Seanslık Değerler (USD/oz):*\n"
        f"• *Sabah (00:00 - 08:00):*\n  `{sabah_str}`\n"
        f"• *Öğle-Avrupa (08:00 - 16:00):*\n  `{ogle_str}`\n"
        f"• *Akşam-Amerika (16:00 - 24:00):*\n  `{aksam_str}`\n"
    )
    return caption


async def run_canli_analysis_report(db: Session, settings) -> str:
    from app.collectors.public_sources import collect_kuveyt_public_silver, collect_global_xag_usd
    from app.models import TechnicalIndicator, PriceSnapshot, Portfolio, Asset
    from app.services.regime import get_market_regime
    from app.services.strategy import StrategyRunner
    from app.agents.orchestrator import run_blended_consensus_resolution
    from app.paper_trading.service import calculate_position

    # Run collectors synchronously to refresh snapshots and indicators
    try:
        collect_kuveyt_public_silver(db, settings=settings)
    except Exception as e:
        logger.warning(f"On-demand collect_kuveyt_public_silver failed: {e}")
        
    try:
        collect_global_xag_usd(db, settings=settings)
    except Exception as e:
        logger.warning(f"On-demand collect_global_xag_usd failed: {e}")

    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    
    stmt = (
        select(TechnicalIndicator)
        .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
        .where(PriceSnapshot.source == "yahoo-si-f")
        .order_by(TechnicalIndicator.bar_timestamp.desc())
        .limit(2)
    )
    indicators = db.execute(stmt).scalars().all()
    if not indicators:
        return "❌ Teknik gösterge verisi bulunamadı."
        
    latest_indicator = indicators[0]
    prev_indicator = indicators[1] if len(indicators) > 1 else None
    
    latest_snapshot = latest_indicator.price_snapshot
    if not latest_snapshot:
        latest_snapshot = db.execute(
            select(PriceSnapshot).where(PriceSnapshot.id == latest_indicator.price_snapshot_id)
        ).scalar_one_or_none()
        
    if not latest_snapshot:
        return "❌ Fiyat snapshot verisi bulunamadı."

    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0
    
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
    
    consensus_event = await run_blended_consensus_resolution(db, regime_info, strategy_votes, latest_snapshot)
    resolved_stance = consensus_event.value_json.get("resolved_stance", "NEUTRAL")
    resolution_markdown = consensus_event.value_json.get("resolution_markdown", "Gerekçe bulunamadı.")

    regime = regime_info.get("regime", "SIDEWAYS")
    regime_label = "Yatay Sakin Piyasa (SIDEWAYS)"
    if regime == "TRENDING_UP":
        regime_label = "Güçlü Yükseliş Trendi (TRENDING UP)"
    elif regime == "TRENDING_DOWN":
        regime_label = "Güçlü Düşüş Trendi (TRENDING DOWN)"

    def format_vote(vote_dict):
        if not vote_dict:
            return "⚪️ BEKLE"
        act = vote_dict.get("action", "HOLD")
        reason = vote_dict.get("reason", "")
        reason_safe = reason.replace("_", " ") if reason else ""
        emoji = "🟢 AL" if act == "BUY" else ("🔴 SAT" if act == "SELL" else "⚪️ BEKLE")
        return f"{emoji} ({reason_safe})" if reason_safe else emoji

    rsi_vote = format_vote(strategy_votes.get("rsi"))
    bb_vote = format_vote(strategy_votes.get("bollinger"))
    sma_vote = format_vote(strategy_votes.get("sma_cross"))

    arbiter_emoji = (
        "🟢 AL" if resolved_stance == "BULLISH" else ("🔴 SAT" if resolved_stance == "BEARISH" else "⚪️ BEKLE")
    )
    arbiter_reason = sanitize_markdown(resolution_markdown)

    price = float(latest_snapshot.mid_price)
    cash_balance = float(portfolio.cash_balance)
    asset_balance = float(current_position.quantity)

    msg = (
        f"📊 *SilverPilot Canlı Analiz Raporu* (İstek Üzerine)\n\n"
        f"🥈 *Gümüş (XAG\\_GRAM):* {price:,.6f} USD/gram\n"
        f"📈 *Piyasa Rejimi:* {regime_label}\n\n"
        f"🗳️ *Strateji Oylaması:*\n"
        f"• RSI (14): {rsi_vote}\n"
        f"• Bollinger Bands: {bb_vote}\n"
        f"• SMA Cross (20/50): {sma_vote}\n\n"
        f"👑 *Yüce Hakem Kararı:* {arbiter_emoji}\n"
        f"📝 *Gerekçe:* {arbiter_reason}\n\n"
        f"💵 *Nakit Bakiyesi:* {cash_balance:,.2f} USD\n"
        f"🥈 *Gümüş Portföyü:* {asset_balance:,.6f} gram\n"
    )
    return msg


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

    cmd = text.strip().lower().split()[0] if text.strip() else ""

    if cmd in ("/canli", "/analiz"):
        try:
            bot = Bot(token=settings.telegram_bot_token)
            
            # Send initial waiting message
            wait_text = (
                "🔄 *Canlı analiz başlatıldı...*\n"
                "Kuveyt Türk ve global XAG fiyatları anlık çekiliyor ve Supreme Arbiter değerlendiriliyor. "
                "Lütfen bekleyin (10-15 sn)..."
            )
            await bot.send_message(chat_id=settings.telegram_chat_id, text=wait_text, parse_mode="Markdown")
            
            if cmd == "/canli":
                with SessionLocal() as db:
                    reply_text = await run_canli_analysis_report(db, settings)
                await bot.send_message(chat_id=settings.telegram_chat_id, text=reply_text, parse_mode="Markdown")
            else:  # /analiz
                # Generate dark mode session chart
                with SessionLocal() as db:
                    chart_buffer = generate_daily_price_chart(db)
                    
                if chart_buffer is None:
                    await bot.send_message(
                        chat_id=settings.telegram_chat_id, 
                        text="❌ Grafik çizimi için yeterli gümüş fiyat geçmişi bulunamadı.", 
                        parse_mode="Markdown"
                    )
                else:
                    with SessionLocal() as db:
                        caption_text = generate_daily_price_caption(db)
                    
                    await bot.send_photo(
                        chat_id=settings.telegram_chat_id,
                        photo=chart_buffer,
                        caption=caption_text,
                        parse_mode="Markdown"
                    )
            return
        except Exception as e:
            logger.exception("Error during on-demand telegram command execution")
            try:
                bot = Bot(token=settings.telegram_bot_token)
                await bot.send_message(
                    chat_id=settings.telegram_chat_id, 
                    text=f"⚠️ Canlı analiz çalıştırılırken bir hata oluştu: {e}", 
                    parse_mode="Markdown"
                )
            except Exception:
                pass
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
