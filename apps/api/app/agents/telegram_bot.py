import asyncio
import logging
import io
import html
import re
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from telegram import Bot, BotCommand
from telegram.error import TelegramError

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Asset, PaperTrade, Portfolio, AgentMemoryEvent, PriceSnapshot
from app.paper_trading.service import calculate_position
from app.services.runtime import trading_status

logger = logging.getLogger("silverpilot.telegram.bot")


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


def handle_telegram_command(command: str, db: Session) -> str:
    parts = command.strip().split()
    if not parts:
        return "Lütfen geçerli bir komut girin."
    cmd = parts[0].lower().split("@")[0]

    if cmd == "/durum":
        return get_durum_text(db)
    elif cmd in ("/sistem", "/status"):
        return get_sistem_text(db)
    elif cmd == "/cuzdan":
        return get_cuzdan_text(db)
    elif cmd == "/karzarar":
        return get_karzarar_text(db)
    elif cmd == "/ajanlar":
        return get_ajanlar_text(db)
    elif cmd in ("/start", "/help"):
        return (
            "🤖 <b>SilverPilot Telegram Portföy & Teşhis Botuna Hoş Geldiniz!</b>\n\n"
            "Aşağıdaki komutları kullanabilirsiniz:\n"
            "📊 <b>/durum</b> - Gümüş & Portföy bakiyelerini ve dağılımını gösterir.\n"
            "🩺 <b>/sistem</b> - Motor, heartbeat, son karar ve neden trade yok özetini gösterir.\n"
            "💼 <b>/cuzdan</b> - $2500 başlangıç bakiyesine göre cüzdan PNL ve değişim oranını gösterir.\n"
            "📈 <b>/karzarar</b> - Açık pozisyon PNL ve son 5 paper-trade işlemini özetler.\n"
            "🤖 <b>/ajanlar</b> - Son Supreme Arbiter uyuşmazlık ve çözümlenmiş kararları listeler."
        )
    else:
        return f"Bilinmeyen komut: {html.escape(cmd)}\nYardım için /help yazabilirsiniz."


def get_sistem_text(db: Session) -> str:
    status = trading_status(db)
    runtime = status.get("runtime") or {}
    latest_decision = status.get("latest_decision") or {}
    latest_collector = status.get("latest_collector_run") or {}
    heartbeats = runtime.get("heartbeats") or []
    auto_heartbeat = next((item for item in heartbeats if item.get("component") == "auto_trader"), None)

    def fmt_dt(value):
        if value is None:
            return "n/a"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M")
        return html.escape(str(value))

    decision_text = "Karar kaydı yok"
    if latest_decision:
        decision_text = (
            f"{html.escape(str(latest_decision.get('action') or 'n/a'))} / "
            f"<code>{html.escape(str(latest_decision.get('reason_code') or 'n/a'))}</code> "
            f"({html.escape(str(latest_decision.get('mode') or 'n/a'))})"
        )

    collector_text = "Collector kaydı yok"
    if latest_collector:
        collector_text = (
            f"{html.escape(str(latest_collector.get('collector_name') or 'n/a'))} "
            f"{html.escape(str(latest_collector.get('status') or 'n/a'))} "
            f"({fmt_dt(latest_collector.get('finished_at') or latest_collector.get('started_at'))})"
        )

    heartbeat_text = "n/a"
    if auto_heartbeat:
        heartbeat_text = (
            f"{html.escape(str(auto_heartbeat.get('status') or 'n/a'))} ({fmt_dt(auto_heartbeat.get('last_seen_at'))})"
        )

    why_no_trade = status.get("why_no_trade") or "Son karar trade engeli bildirmiyor"

    return (
        "🩺 <b>SilverPilot Sistem Özeti</b>\n\n"
        f"⚙️ <b>Runtime:</b> {html.escape(str(runtime.get('status') or 'unknown'))}\n"
        f"💓 <b>Auto-trader heartbeat:</b> {heartbeat_text}\n"
        f"🧠 <b>Son karar:</b> {decision_text}\n"
        f"📡 <b>Son collector:</b> {collector_text}\n"
        f"🚦 <b>Neden trade yok?:</b> <code>{html.escape(str(why_no_trade))}</code>"
    )


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
        "📊 <b>Gümüş & Portföy Durumu</b>\n\n"
        f"💵 <b>Nakitteki Bakiye:</b> {cash_balance:,.2f} USD\n"
        f"🥈 <b>Gümüş Miktarı:</b> {silver_qty:,.4f} XAG_GRAM\n"
        f"💰 <b>Gümüş Değeri:</b> {silver_value:,.2f} USD\n"
        f"📈 <b>Toplam Portföy Değeri:</b> {portfolio_value:,.2f} USD\n"
        f"⚖️ <b>Portföy Dağılımı:</b> %{ratio:.2f} Gümüş / %{cash_ratio:.2f} Nakit"
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

    initial_balance = Decimal("2500")
    pnl = portfolio_value - initial_balance
    pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else Decimal("0")

    sign = "+" if pnl >= 0 else ""

    return (
        "💼 <b>Cüzdan Değişim Özeti</b>\n\n"
        f"💵 <b>Başlangıç Bakiyesi:</b> $2500.00 USD\n"
        f"📈 <b>Anlık Portföy Değeri:</b> ${portfolio_value:,.2f} USD\n"
        f"📊 <b>Toplam Kar/Zarar (PNL):</b> {sign}${pnl:,.2f} USD ({sign}{pnl_pct:.2f}%)"
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

    # Portfolio value & PNL calculations
    portfolio_value = portfolio.cash_balance + (silver_qty * mid_price)
    initial_balance = Decimal("2500")
    total_pnl = portfolio_value - initial_balance

    unrealized_pnl = Decimal("0")
    if silver_qty > 0:
        unrealized_pnl = silver_qty * (mid_price - avg_buy_cost)

    realized_pnl = total_pnl - unrealized_pnl

    sign_unrealized = "+" if unrealized_pnl >= 0 else ""
    sign_realized = "+" if realized_pnl >= 0 else ""
    sign_total = "+" if total_pnl >= 0 else ""

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
                f"{idx}. {action_emoji} | Miktar: {trade.quantity:,.4f} @ {trade.price:,.4f} USD ({time_str})\n"
            )
    else:
        trades_str = "<i>Henüz bir paper-trade işlemi bulunmuyor.</i>"

    return (
        "📈 <b>Açık Pozisyon ve Kar/Zarar Durumu</b>\n\n"
        f"🥈 <b>Açık Pozisyon:</b> {silver_qty:,.4f} XAG_GRAM\n"
        f"🏷️ <b>Ortalama Alış Maliyeti:</b> {avg_buy_cost:,.4f} USD/gram\n"
        f"💸 <b>Anlık Gümüş Fiyatı:</b> {mid_price:,.4f} USD/gram\n\n"
        f"📊 <b>Açık Pozisyon Kar/Zarar:</b> {sign_unrealized}${unrealized_pnl:,.2f} USD\n"
        f"💰 <b>Gerçekleşen Kar/Zarar:</b> {sign_realized}${realized_pnl:,.2f} USD\n"
        f"🏆 <b>Toplam Net Kar/Zarar:</b> {sign_total}${total_pnl:,.2f} USD\n\n"
        f"🔄 <b>Son 5 Paper Trade İşlemi:</b>\n{trades_str}"
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

    lines = ["🤖 <b>Ajan Teşhis & Supreme Arbiter Kararları</b>"]

    lines.append("\n🚨 <b>Son Uyuşmazlıklar (Agent Disagreements):</b>")
    if disagreements:
        for dis in disagreements:
            val = dis.value_json or {}
            stances = val.get("stances", {})
            stances_str = ", ".join(f"{k}: {v}" for k, v in stances.items())
            time_str = dis.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"• <b>[{time_str}]</b> Stances: <code>{html.escape(stances_str)}</code>")
            for d in val.get("disagreements", []):
                desc_safe = escape_html_response(d.get("description", ""))
                lines.append(f"  └─ <code>{html.escape(d.get('type', ''))}</code>: {desc_safe}")
    else:
        lines.append("<i>Yakın zamanda bir uyuşmazlık tespit edilmedi.</i>")

    lines.append("\n⚖️ <b>Son Arbiter Kararları (Resolutions):</b>")
    if resolutions:
        for res in resolutions:
            val = res.value_json or {}
            resolved_stance = val.get("resolved_stance", "NEUTRAL")
            confidence = val.get("confidence", 0.5)
            resolution_markdown = val.get("resolution_markdown", "")
            time_str = res.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"• <b>[{time_str}]</b> Karar: <b>{resolved_stance}</b> (Güven: {confidence:.2f})")
            short_res = resolution_markdown[:150] + "..." if len(resolution_markdown) > 150 else resolution_markdown
            short_res_safe = escape_html_response(short_res)
            lines.append(f"  └─ {short_res_safe}")
    else:
        lines.append("<i>Henüz çözümlenmiş bir arbiter kararı bulunmuyor.</i>")

    return "\n".join(lines)


def generate_daily_price_chart(db: Session) -> io.BytesIO | None:
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return None

    # Try kuveyt first
    stmt = (
        select(PriceSnapshot)
        .where(
            PriceSnapshot.asset_id == asset.id,
            PriceSnapshot.source == "kuveyt-public-silver-page",
            PriceSnapshot.observed_at >= twenty_four_hours_ago,
        )
        .order_by(PriceSnapshot.observed_at.asc())
    )
    snapshots = db.execute(stmt).scalars().all()

    if not snapshots:
        stmt = (
            select(PriceSnapshot)
            .where(
                PriceSnapshot.asset_id == asset.id,
                PriceSnapshot.source.in_(["yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"]),
                PriceSnapshot.observed_at >= twenty_four_hours_ago,
            )
            .order_by(PriceSnapshot.observed_at.asc())
        )
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
    fig.patch.set_facecolor("#121212")
    ax.set_facecolor("#1e1e1e")

    # Plot line
    ax.plot(times, prices, color="#00e5ff", linewidth=2.5, label="Gümüş (XAG_GRAM/USD) Orta Fiyat")

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
        b2 = boundaries[i + 1]

        # Intersection
        i_start = max(b1, min_time)
        i_end = min(b2, max_time)

        if i_start >= i_end:
            continue

        # Determine session
        if b1.hour == 0:
            color = "#007acc"
            label = "Sabah Seansı\n(00:00 - 08:00)"
            alpha = 0.08
        elif b1.hour == 8:
            color = "#d4af37"
            label = "Öğle-Avrupa Seansı\n(08:00 - 16:00)"
            alpha = 0.08
        else:
            color = "#8a2be2"
            label = "Akşam-Amerika Seansı\n(16:00 - 24:00)"
            alpha = 0.08

        ax.axvspan(i_start, i_end, color=color, alpha=alpha)

        # Place label if the span is wide enough (at least 2 hours)
        span_hours = (i_end - i_start).total_seconds() / 3600.0
        if span_hours >= 2.0:
            mid_x = i_start + (i_end - i_start) / 2
            ax.text(mid_x, label_y, label, color=color, ha="center", va="top", fontsize=8.5, weight="bold")

    # Formatting axes
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tr_tz))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))

    ax.tick_params(colors="#888888", labelsize=9)
    ax.grid(True, color="#2d2d2d", linestyle="--", linewidth=0.5)

    # Labels and titles
    ax.set_title(
        "🥈 SilverPilot Gümüş (XAG_GRAM) Günlük Fiyat Değişim Analizi 📊",
        color="#ffffff",
        fontsize=13,
        weight="bold",
        pad=25,
    )
    ax.set_ylabel("Fiyat (USD/gram)", color="#888888", fontsize=10, labelpad=10)

    # Style border
    for spine in ax.spines.values():
        spine.set_color("#2d2d2d")

    # Legend
    legend = ax.legend(loc="lower right", facecolor="#1e1e1e", edgecolor="#2d2d2d")
    for text in legend.get_texts():
        text.set_color("#ffffff")

    plt.tight_layout()

    # Save to BytesIO
    buf = io.BytesIO()
    plt.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_daily_price_caption(db: Session) -> str:
    now = datetime.now(timezone.utc)
    twenty_four_hours_ago = now - timedelta(hours=24)

    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return "📊 <b>Seanslık Fiyat Analiz Özeti</b>\nVeri bulunamadı."

    stmt = (
        select(PriceSnapshot)
        .where(
            PriceSnapshot.asset_id == asset.id,
            PriceSnapshot.source == "kuveyt-public-silver-page",
            PriceSnapshot.observed_at >= twenty_four_hours_ago,
        )
        .order_by(PriceSnapshot.observed_at.asc())
    )
    snapshots = db.execute(stmt).scalars().all()

    if not snapshots:
        stmt = (
            select(PriceSnapshot)
            .where(
                PriceSnapshot.asset_id == asset.id,
                PriceSnapshot.source.in_(["yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"]),
                PriceSnapshot.observed_at >= twenty_four_hours_ago,
            )
            .order_by(PriceSnapshot.observed_at.asc())
        )
        snapshots = db.execute(stmt).scalars().all()

    if not snapshots:
        return "📊 <b>Seanslık Fiyat Analiz Özeti</b>\nVeri bulunamadı."

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
        return f"Min: {min(lst):.3f} | Max: {max(lst):.3f} | Ort: {sum(lst) / len(lst):.3f}"

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
        "📊 <b>SilverPilot Günlük Seans & Fiyat Raporu</b>\n\n"
        f"🥈 <b>Son Fiyat (Canlı):</b> {latest_price:.4f} USD/gram\n"
        f"📈 <b>Günlük Değişim:</b> {sign}{daily_change:.4f} USD ({sign}{daily_change_pct:.2f}%)\n"
        f"⚖️ <b>Günlük Aralık:</b> {overall_min:.4f} - {overall_max:.4f} USD/gram\n\n"
        "🕰️ <b>Seanslık Değerler (USD/gram):</b>\n"
        f"• <b>Sabah (00:00 - 08:00):</b>\n  <code>{sabah_str}</code>\n"
        f"• <b>Öğle-Avrupa (08:00 - 16:00):</b>\n  <code>{ogle_str}</code>\n"
        f"• <b>Akşam-Amerika (16:00 - 24:00):</b>\n  <code>{aksam_str}</code>\n"
    )
    return caption


async def run_canli_analysis_report(db: Session, settings) -> str:
    from app.collectors.public_sources import collect_kuveyt_public_silver, collect_global_xag_usd
    from app.models import PriceSnapshot, Portfolio, Asset
    from app.services.regime import get_market_regime
    from app.services.strategy import StrategyRunner
    from app.agents.orchestrator import run_blended_consensus_resolution
    from app.paper_trading.service import calculate_position
    from app.services.indicator_readiness import get_latest_indicator_context
    from app.services.auto_trader import (
        build_timeframe_indicator_summary,
        evaluate_timeframe_guardrails,
        format_readiness_block_report,
        get_strategy_timeframe_contexts,
        summarize_timeframe_inputs,
    )

    portfolio = db.execute(select(Portfolio).where(Portfolio.name == "gram-paper")).scalar_one_or_none()
    asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if not asset:
        return "❌ Gümüş (XAG_GRAM) varlığı bulunamadı."

    timeframe_contexts = get_strategy_timeframe_contexts(db, asset.symbol)
    readiness_block_flags = evaluate_timeframe_guardrails(timeframe_contexts)
    if readiness_block_flags:
        snapshot = None
        for timeframe in ("5m", "1h", "1d"):
            indicator = timeframe_contexts[timeframe].readiness.indicator
            if indicator is None:
                continue
            snapshot = indicator.price_snapshot
            if snapshot is None and indicator.price_snapshot_id is not None:
                snapshot = db.execute(
                    select(PriceSnapshot).where(PriceSnapshot.id == indicator.price_snapshot_id)
                ).scalar_one_or_none()
            if snapshot is not None:
                break

        position_quantity = Decimal("0")
        cash_balance = Decimal("0")
        if portfolio is not None:
            position = calculate_position(db, portfolio.id, asset.id)
            position_quantity = position.quantity
            cash_balance = portfolio.cash_balance

        return format_readiness_block_report(
            {
                "action": "HOLD",
                "price": float(snapshot.mid_price) if snapshot is not None else 0.0,
                "cash_balance": float(cash_balance),
                "xag_balance": float(position_quantity),
                "reason_code": readiness_block_flags[0],
                "readiness_block_flags": readiness_block_flags,
                "timeframe_inputs": summarize_timeframe_inputs(timeframe_contexts),
                "timeframe_indicators": build_timeframe_indicator_summary(timeframe_contexts),
                "notification_kind": "readiness_block",
            }
        )

    # Run collectors synchronously to refresh snapshots and indicators
    try:
        collect_kuveyt_public_silver(db, settings=settings)
    except Exception as e:
        logger.warning("On-demand collect_kuveyt_public_silver failed; error_type=%s.", type(e).__name__)

    try:
        collect_global_xag_usd(db, settings=settings)
    except Exception as e:
        logger.warning("On-demand collect_global_xag_usd failed; error_type=%s.", type(e).__name__)

    indicator_context = get_latest_indicator_context(db, asset_symbol=asset.symbol)
    readiness = indicator_context.readiness
    if not readiness.usable or readiness.indicator is None:
        return (
            "❌ Teknik gösterge verisi hazır değil.\n"
            f"Durum: {readiness.status}\n"
            f"Nedenler: {', '.join(readiness.reason_codes) if readiness.reason_codes else 'Yok'}"
        )

    latest_indicator = readiness.indicator
    prev_indicator = indicator_context.previous_indicator

    latest_snapshot = latest_indicator.price_snapshot
    if not latest_snapshot:
        latest_snapshot = db.execute(
            select(PriceSnapshot).where(PriceSnapshot.id == latest_indicator.price_snapshot_id)
        ).scalar_one_or_none()

    if not latest_snapshot:
        return "❌ Fiyat snapshot verisi bulunamadı."

    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0

    regime_info = get_market_regime(db, asset_symbol=asset.symbol, timeframe=readiness.timeframe)
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
    resolution_markdown = (consensus_event.value_json.get("resolution_markdown") or "").strip()
    if not resolution_markdown:
        resolution_markdown = "Arbiter gerekçesi boş döndü; teknik oylar ve rejim üzerinden beklemede kalındı."

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
    arbiter_reason = escape_html_response(resolution_markdown)
    indicator_details = (
        f"\n📊 <b>Teknik Göstergeler:</b>\n"
        f"• RSI (14): {float(latest_indicator.rsi_14 or 0.0):,.2f}\n"
        f"• SMA (20/50): {float(latest_indicator.sma_20 or 0.0):,.4f} / {float(latest_indicator.sma_50 or 0.0):,.4f}\n"
        f"• Bollinger (U/L): {float(latest_indicator.bb_upper_20_2 or 0.0):,.4f} / {float(latest_indicator.bb_lower_20_2 or 0.0):,.4f}\n"
    )

    price = float(latest_snapshot.mid_price)
    cash_balance = float(portfolio.cash_balance)
    xag_balance = float(current_position.quantity)

    msg = (
        f"📊 <b>SilverPilot Canlı Analiz Raporu</b> (İstek Üzerine)\n\n"
        f"🥈 <b>Gümüş (XAG_GRAM):</b> {price:,.4f} USD/gram\n"
        f"📈 <b>Piyasa Rejimi:</b> {regime_label}\n\n"
        f"🗳️ <b>Strateji Oylaması:</b>\n"
        f"• RSI (14): {rsi_vote}\n"
        f"• Bollinger Bands: {bb_vote}\n"
        f"• SMA Cross (20/50): {sma_vote}\n\n"
        f"👑 <b>Yüce Hakem Kararı:</b> {arbiter_emoji}\n"
        f"📝 <b>Gerekçe:</b> {arbiter_reason}\n\n"
        f"💵 <b>Nakit Bakiyesi:</b> {cash_balance:,.2f} USD\n"
        f"🥈 <b>Gümüş Portföyü:</b> {xag_balance:,.4f} XAG_GRAM\n"
        f"{indicator_details}"
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
                "🔄 <b>Canlı analiz başlatıldı...</b>\n"
                "Kuveyt Türk ve global XAG_GRAM fiyatları anlık çekiliyor ve Supreme Arbiter değerlendiriliyor. "
                "Lütfen bekleyin (10-15 sn)..."
            )
            await bot.send_message(chat_id=settings.telegram_chat_id, text=wait_text, parse_mode="HTML")

            if cmd == "/canli":
                with SessionLocal() as db:
                    reply_text = await run_canli_analysis_report(db, settings)
                await bot.send_message(chat_id=settings.telegram_chat_id, text=reply_text, parse_mode="HTML")
            else:  # /analiz
                # Generate dark mode session chart
                with SessionLocal() as db:
                    chart_buffer = generate_daily_price_chart(db)

                if chart_buffer is None:
                    await bot.send_message(
                        chat_id=settings.telegram_chat_id,
                        text="❌ Grafik çizimi için yeterli gümüş fiyat geçmişi bulunamadı.",
                        parse_mode="HTML",
                    )
                else:
                    with SessionLocal() as db:
                        caption_text = generate_daily_price_caption(db)

                    await bot.send_photo(
                        chat_id=settings.telegram_chat_id,
                        photo=chart_buffer,
                        caption=caption_text,
                        parse_mode="HTML",
                    )
            return
        except Exception as e:
            logger.error("Error during on-demand telegram command execution; error_type=%s.", type(e).__name__)
            try:
                bot = Bot(token=settings.telegram_bot_token)
                await bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=f"⚠️ Canlı analiz çalıştırılırken bir hata oluştu: {html.escape(str(e))}",
                    parse_mode="HTML",
                )
            except Exception as send_err:
                logger.error(
                    "Failed to send error notification to Telegram; error_type=%s.",
                    type(send_err).__name__,
                )
            return

    try:
        with SessionLocal() as db:
            reply_text = handle_telegram_command(text, db)
    except Exception as e:
        logger.error("Database error while processing Telegram command; error_type=%s.", type(e).__name__)
        reply_text = f"⚠️ Komut işlenirken bir veritabanı hatası oluştu: {html.escape(str(e))}"

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(chat_id=settings.telegram_chat_id, text=reply_text, parse_mode="HTML")
    except Exception as e:
        logger.error("Failed to send Telegram message; error_type=%s.", type(e).__name__)


async def register_bot_commands(bot: Bot) -> None:
    """Programmatically registers the bot commands in the Telegram API so they show up in the Telegram UI menu."""
    commands = [
        BotCommand("durum", "Gümüş & Portföy bakiyelerini ve dağılımını gösterir"),
        BotCommand("sistem", "Motor, heartbeat, son karar ve trade blok nedenini özetler"),
        BotCommand("cuzdan", "$2500 başlangıç bakiyesine göre cüzdan PNL ve değişim oranını gösterir"),
        BotCommand("karzarar", "Açık pozisyon PNL ve son 5 paper-trade işlemini özetler"),
        BotCommand("ajanlar", "Son Supreme Arbiter uyuşmazlık ve çözümlenmiş kararları listeler"),
        BotCommand("canli", "Canlı fiyat analizi, indikatörler ve Supreme Arbiter raporu sunar"),
        BotCommand("analiz", "Son seanslık fiyat analiz grafiğini fotoğraf olarak gönderir"),
        BotCommand("help", "Kullanılabilir komutları ve yardım kılavuzunu gösterir"),
    ]
    try:
        logger.info("Registering Telegram bot commands programmatically...")
        await bot.set_my_commands(commands)
        logger.info("Telegram bot commands successfully registered.")
    except Exception as e:
        logger.error("Failed to register Telegram bot commands; error_type=%s.", type(e).__name__)


async def set_telegram_webhook():
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram Bot Token is not configured. Webhook will not be set.")
        return

    if not settings.telegram_webhook_url:
        logger.warning("Telegram Webhook URL is not configured. Webhook registration skipped.")
        return

    bot = Bot(token=settings.telegram_bot_token)
    await register_bot_commands(bot)
    webhook_url = f"{settings.telegram_webhook_url.rstrip('/')}/agent/telegram/webhook"
    logger.info("Setting Telegram webhook for configured public endpoint.")

    try:
        await bot.set_webhook(url=webhook_url)
        logger.info("Telegram webhook successfully registered.")
    except Exception as e:
        logger.error("Failed to set Telegram webhook; error_type=%s.", type(e).__name__)


async def start_polling():
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram Bot Token is not configured. Polling will not start.")
        return

    bot = Bot(token=settings.telegram_bot_token)
    await register_bot_commands(bot)
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
            logger.error("Telegram error in polling loop; error_type=%s.", type(e).__name__)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Unexpected error in polling; error_type=%s.", type(e).__name__)
            await asyncio.sleep(5)
