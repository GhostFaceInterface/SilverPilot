import logging
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Portfolio, Signal, AgentMemoryEvent, NotificationAudit
from app.services.strategy import StrategyDecision, StrategyRunner, STRATEGY_REGISTRY
from app.paper_trading.service import calculate_position
from app.services.indicator_readiness import (
    STRATEGY_TIMEFRAME_ROLES,
    get_latest_indicator_context,
    get_strategy_timeframe_policy,
)
from app.services.runtime import (
    AUTO_TRADER_COMPONENT,
    finish_trading_decision_run,
    record_runtime_heartbeat,
    source_health_snapshot,
    start_trading_decision_run,
    to_jsonable,
)
from app.services.policy_resolver import resolve_strategy_policy
from app.services.source_divergence import SOURCE_DIVERGENCE_BLOCK, evaluate_source_divergence
from app.services.trade_intents import TradeIntent, execute_trade_intent

logger = logging.getLogger("silverpilot.services.auto_trader")

ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_HOLD = "HOLD"
BLOCKED_CONFIG_INVALID = "BLOCKED_CONFIG_INVALID"
BLOCKED_REASON_CODES = {BLOCKED_CONFIG_INVALID}
READINESS_BLOCK_REASONS = {
    "DAILY_BAR_DELAYED",
    "MARKET_CLOSED",
    "ENTRY_TIMEFRAME_STALE",
    "EXECUTION_TIMEFRAME_STALE",
    "INSUFFICIENT_HISTORY",
    "DAILY_TREND_MISSING",
    "ENTRY_TIMEFRAME_UNUSABLE",
    "EXECUTION_TIMEFRAME_UNUSABLE",
    "TIMEFRAME_SOURCE_MISMATCH",
    SOURCE_DIVERGENCE_BLOCK,
}

READINESS_REASON_LABELS = {
    "DAILY_BAR_DELAYED": "Günlük COMEX barı grace süresi sonrası gecikti",
    "MARKET_CLOSED": "COMEX piyasası kapalı",
    "INSUFFICIENT_HISTORY": "Günlük trend verisi hazır değil; göstergeler için yeterli geçmiş bar yok",
    "DAILY_TREND_MISSING": "Günlük trend verisi hazır değil",
    "ENTRY_TIMEFRAME_STALE": "Saatlik giriş verisi güncel değil",
    "ENTRY_TIMEFRAME_UNUSABLE": "Saatlik giriş verisi kullanılamıyor",
    "EXECUTION_TIMEFRAME_STALE": "5 dakikalık uygulama verisi güncel değil",
    "EXECUTION_TIMEFRAME_UNUSABLE": "5 dakikalık uygulama verisi kullanılamıyor",
    "TIMEFRAME_SOURCE_MISMATCH": "Zaman dilimi veri kaynakları uyumsuz",
    SOURCE_DIVERGENCE_BLOCK: "Banka fiyatı ile global XAG/USD dönüşümü ayrıştı",
}


@dataclass(frozen=True)
class DecisionContext:
    requested_strategy: str
    active_strategy: str
    portfolio: Portfolio
    asset: Asset
    latest_snapshot: object
    latest_indicator: object | None
    daily_context: object
    hourly_context: object
    execution_context: object
    timeframe_contexts: dict
    readiness_block_flags: list[str]
    source_divergence: dict | None
    has_open_position: bool
    news_sentiment: str
    latest_event: AgentMemoryEvent | None


@dataclass(frozen=True)
class StrategyResolution:
    action: str
    candidate_action: str
    reason_code: str
    confidence: Decimal
    details: dict
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    expected_exit_price: Decimal | None = None
    resolved_strategy: str | None = None
    exit_metadata: dict | None = None

    @property
    def is_blocked(self) -> bool:
        return self.reason_code in BLOCKED_REASON_CODES


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    skipped_reason: str | None
    trade_id: int | None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "skipped_reason": self.skipped_reason,
            "trade_id": self.trade_id,
        }


@dataclass(frozen=True)
class NotificationDecision:
    sent: bool
    skipped_reason: str | None
    cooldown_seconds: int

    def as_dict(self) -> dict:
        return {
            "sent": self.sent,
            "skipped_reason": self.skipped_reason,
            "cooldown_seconds": self.cooldown_seconds,
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


def _format_optional_float(value, *, precision: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):,.{precision}f}"
    except (TypeError, ValueError):
        return "n/a"


def build_timeframe_indicator_summary(timeframe_contexts: dict) -> dict:
    summary = {}
    for timeframe, context in timeframe_contexts.items():
        indicator = context.readiness.indicator
        if indicator is None:
            continue
        summary[timeframe] = {
            "close": float(indicator.close_usd_oz) if indicator.close_usd_oz is not None else None,
            "rsi": float(indicator.rsi_14) if indicator.rsi_14 is not None else None,
            "sma_20": float(indicator.sma_20) if indicator.sma_20 is not None else None,
            "sma_50": float(indicator.sma_50) if indicator.sma_50 is not None else None,
            "bb_upper": float(indicator.bb_upper_20_2) if indicator.bb_upper_20_2 is not None else None,
            "bb_lower": float(indicator.bb_lower_20_2) if indicator.bb_lower_20_2 is not None else None,
        }
    return summary


def format_readiness_block_report(trade_data: dict) -> str:
    reason_code = trade_data.get("reason_code") or _select_block_reason(trade_data.get("readiness_block_flags") or [])
    reason_label = READINESS_REASON_LABELS.get(reason_code, reason_code or "Readiness blok nedeni bilinmiyor")
    timeframe_inputs = trade_data.get("timeframe_inputs") or {}
    timeframe_indicators = trade_data.get("timeframe_indicators") or {}

    timeframe_lines = []
    timeframe_labels = {"1d": "1d trend", "1h": "1h giriş", "5m": "5m uygulama"}
    for timeframe in ("1d", "1h", "5m"):
        info = timeframe_inputs.get(timeframe) or {}
        status = info.get("status") or "unknown"
        usable = "hazır" if info.get("usable") else "hazır değil"
        source = info.get("source") or "n/a"
        age = info.get("age_minutes")
        age_text = f"{age} dk" if age is not None else "n/a"
        reason_codes = info.get("reason_codes") or []
        reasons = ", ".join(reason_codes) if reason_codes else "Yok"
        timeframe_lines.append(
            f"• <b>{timeframe_labels[timeframe]}:</b> {html.escape(status)} / {usable} | "
            f"kaynak: <code>{html.escape(str(source))}</code> | yaş: {html.escape(str(age_text))} | "
            f"nedenler: <code>{html.escape(reasons)}</code>"
        )

    indicator_lines = []
    for timeframe in ("1h", "5m"):
        values = timeframe_indicators.get(timeframe)
        if not values:
            continue
        indicator_lines.append(
            f"• <b>{timeframe}:</b> kapanış {_format_optional_float(values.get('close'))} USD/gram, "
            f"RSI {_format_optional_float(values.get('rsi'), precision=2)}, "
            f"SMA20/50 {_format_optional_float(values.get('sma_20'))} / {_format_optional_float(values.get('sma_50'))}, "
            f"BB U/L {_format_optional_float(values.get('bb_upper'))} / {_format_optional_float(values.get('bb_lower'))}"
        )
    if not indicator_lines:
        indicator_lines.append("• Kullanılabilir 1h/5m teknik değer bulunamadı.")

    msg = (
        "⚠️ <b>SilverPilot İşlem Blok Raporu</b>\n\n"
        f"🥈 <b>Gümüş (XAG_GRAM):</b> {trade_data['price']:,.4f} USD/gram\n"
        f"🔒 <b>Ana Gerekçe:</b> {html.escape(reason_label)}\n"
        f"🔍 <b>Neden Kodu:</b> <code>{html.escape(str(reason_code or 'UNKNOWN'))}</code>\n\n"
        "<b>Readiness Durumu:</b>\n"
        f"{chr(10).join(timeframe_lines)}\n\n"
        "<b>Bilgi Amaçlı Teknik Değerler:</b>\n"
        f"{chr(10).join(indicator_lines)}\n\n"
        f"🔄 <b>İşlem Durumu:</b> ⚪️ BEKLE (HOLD)\n"
        f"💵 <b>Nakit Bakiyesi:</b> {trade_data.get('cash_balance', 0.0):,.2f} USD\n"
    )
    if "xag_balance" in trade_data:
        msg += f"🥈 <b>Gümüş Portföyü:</b> {trade_data['xag_balance']:,.4f} XAG_GRAM\n"
    return msg


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

    is_readiness_block = trade_data.get("notification_kind") == "readiness_block"
    is_blended = (
        trade_data.get("strategy_name") == "blended"
        and bool(trade_data.get("strategy_votes"))
        and bool(trade_data.get("arbiter_decision"))
    )

    if is_readiness_block:
        msg = format_readiness_block_report(trade_data)
    elif is_blended:
        regime_info = trade_data.get("regime_info") or {}
        regime_label = "Yatay Sakin Piyasa (SIDEWAYS)"
        REGIME_MAP = {
            "TRENDING_UP": "Güçlü Yükseliş Trendi (TRENDING UP)",
            "TRENDING_DOWN": "Güçlü Düşüş Trendi (TRENDING DOWN)",
        }
        regime = regime_info.get("regime", "SIDEWAYS")
        regime_label = REGIME_MAP.get(regime, "Yatay Sakin Piyasa (SIDEWAYS)")

        votes = trade_data.get("strategy_votes") or {}

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
        if not arbiter_reason.strip():
            arbiter_reason = "Arbiter gerekçesi boş döndü; teknik oylar ve rejim üzerinden beklemede kalındı."

        indicator_details = ""
        indicators = trade_data.get("indicators") or {}
        if indicators:
            indicator_details = (
                f"\n📊 <b>Teknik Göstergeler:</b>\n"
                f"• RSI (14): {indicators.get('rsi', 0.0):,.2f}\n"
                f"• SMA (20/50): {indicators.get('sma_20', 0.0):,.4f} / {indicators.get('sma_50', 0.0):,.4f}\n"
                f"• Bollinger (U/L): {indicators.get('bb_upper', 0.0):,.4f} / {indicators.get('bb_lower', 0.0):,.4f}\n"
            )

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
        msg += indicator_details

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


def _select_block_reason(strategy_readiness_flags: list[str]) -> str | None:
    prioritized_block_flags = [
        SOURCE_DIVERGENCE_BLOCK,
        "TIMEFRAME_SOURCE_MISMATCH",
        "MARKET_CLOSED",
        "DAILY_BAR_DELAYED",
        "ENTRY_TIMEFRAME_STALE",
        "EXECUTION_TIMEFRAME_STALE",
        "INSUFFICIENT_HISTORY",
        "ENTRY_TIMEFRAME_UNUSABLE",
        "DAILY_TREND_MISSING",
        "EXECUTION_TIMEFRAME_UNUSABLE",
    ]
    return next((flag for flag in prioritized_block_flags if flag in strategy_readiness_flags), None)


def _base_strategy_details(context: DecisionContext) -> dict:
    return {
        "strategy_name": context.active_strategy,
        "timeframe_policy": dict(STRATEGY_TIMEFRAME_ROLES),
        "timeframe_inputs": summarize_timeframe_inputs(context.timeframe_contexts),
        "timeframe_indicators": build_timeframe_indicator_summary(context.timeframe_contexts),
        "agent_sentiment": context.news_sentiment,
        "readiness_block_flags": context.readiness_block_flags,
        "source_divergence": context.source_divergence,
    }


def _blocked_strategy_resolution(
    context: DecisionContext, *, reason_code: str, confidence: Decimal
) -> StrategyResolution:
    details = _base_strategy_details(context)
    return StrategyResolution(
        action=ACTION_HOLD,
        candidate_action=ACTION_HOLD,
        reason_code=reason_code,
        confidence=confidence,
        details=details,
        resolved_strategy=context.active_strategy,
        exit_metadata={},
    )


def _invalid_strategy_resolution(context: DecisionContext) -> StrategyResolution:
    details = _base_strategy_details(context)
    details["config_error"] = f"Strategy {context.active_strategy} not registered in STRATEGY_REGISTRY"
    return StrategyResolution(
        action=ACTION_HOLD,
        candidate_action=ACTION_HOLD,
        reason_code=BLOCKED_CONFIG_INVALID,
        confidence=Decimal("0.9900"),
        details=details,
        resolved_strategy=None,
        exit_metadata={},
    )


async def _resolve_strategy_resolution(db: Session, context: DecisionContext) -> StrategyResolution:
    if context.active_strategy not in STRATEGY_REGISTRY:
        return _invalid_strategy_resolution(context)

    block_reason = _select_block_reason(context.readiness_block_flags)
    if block_reason is not None:
        confidence_map = {
            "TIMEFRAME_SOURCE_MISMATCH": Decimal("0.9900"),
            "MARKET_CLOSED": Decimal("0.9900"),
            "DAILY_BAR_DELAYED": Decimal("0.9900"),
            "ENTRY_TIMEFRAME_STALE": Decimal("0.9800"),
            "EXECUTION_TIMEFRAME_STALE": Decimal("0.9800"),
            "INSUFFICIENT_HISTORY": Decimal("0.9800"),
            "ENTRY_TIMEFRAME_UNUSABLE": Decimal("0.9800"),
            "DAILY_TREND_MISSING": Decimal("0.9900"),
            SOURCE_DIVERGENCE_BLOCK: Decimal("0.9900"),
        }
        return _blocked_strategy_resolution(
            context,
            reason_code=block_reason,
            confidence=confidence_map.get(block_reason, Decimal("0.9700")),
        )

    strategy = STRATEGY_REGISTRY[context.active_strategy]
    latest_indicator = context.latest_indicator
    hourly_context = context.hourly_context

    atr_value = (
        Decimal(str(latest_indicator.atr_14)) if (latest_indicator and latest_indicator.atr_14 is not None) else None
    )
    close_value = (
        Decimal(str(latest_indicator.close_usd_oz))
        if (latest_indicator and latest_indicator.close_usd_oz is not None)
        else None
    )

    strategy_context = {
        "close": latest_indicator.close_usd_oz if latest_indicator else None,
        "rsi_14": latest_indicator.rsi_14 if latest_indicator else None,
        "sma_20": latest_indicator.sma_20 if latest_indicator else None,
        "sma_50": latest_indicator.sma_50 if latest_indicator else None,
        "prev_sma_20": (
            hourly_context.previous_indicator.sma_20
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        ),
        "prev_sma_50": (
            hourly_context.previous_indicator.sma_50
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        ),
        "bb_lower": latest_indicator.bb_lower_20_2 if latest_indicator else None,
        "bb_upper": latest_indicator.bb_upper_20_2 if latest_indicator else None,
        "macd_line": latest_indicator.macd_line if latest_indicator else None,
        "macd_signal": latest_indicator.macd_signal if latest_indicator else None,
        "prev_macd_line": (
            hourly_context.previous_indicator.macd_line
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        ),
        "prev_macd_signal": (
            hourly_context.previous_indicator.macd_signal
            if (hourly_context.previous_indicator and latest_indicator)
            else None
        ),
        "atr_value": atr_value,
        "close_value": close_value,
        "has_open_position": context.has_open_position,
        "asset": context.asset,
        "hourly_context": hourly_context,
        "daily_context": context.daily_context,
        "latest_indicator": latest_indicator,
        "latest_snapshot": context.latest_snapshot,
        "latest_event": context.latest_event,
        "readiness_block_flags": context.readiness_block_flags,
    }

    strategy_decision: StrategyDecision = await strategy.evaluate(db, strategy_context)
    details = {
        **_base_strategy_details(context),
        **strategy_decision.to_signal_details(),
    }
    if strategy_decision.exit_metadata:
        details.update(strategy_decision.exit_metadata)

    return StrategyResolution(
        action=strategy_decision.action,
        candidate_action=strategy_decision.action,
        reason_code=strategy_decision.reason_code,
        confidence=strategy_decision.confidence,
        stop_loss_price=strategy_decision.stop_loss_price,
        take_profit_price=strategy_decision.take_profit_price,
        expected_exit_price=strategy_decision.expected_exit_price,
        details=details,
        resolved_strategy=context.active_strategy,
        exit_metadata=strategy_decision.exit_metadata or {},
    )


async def _run_auto_trading_impl(db: Session, settings):
    # 0. Pazartesi Isınma Süresi Kontrolü (Indicator Warmup)
    # Pazar 18:00 - 18:05 ET arası (piyasa açılışının ilk 5 dakikası) işlemler ertelenir
    from datetime import timezone
    from zoneinfo import ZoneInfo

    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(timezone.utc).astimezone(et_tz)
    record_runtime_heartbeat(
        db,
        component=AUTO_TRADER_COMPONENT,
        status="ok",
        expected_interval_seconds=settings.collector_interval_seconds,
        details={"mode": settings.auto_trading_mode, "strategy_name": settings.strategy_name},
    )
    decision_run = start_trading_decision_run(
        db,
        mode=settings.auto_trading_mode,
        asset_symbol=settings.auto_trading_asset_symbol,
        strategy_name=settings.strategy_name or "strategy_v2",
        details={"trigger": "auto_trader_loop"},
    )
    if now_et.weekday() == 6 and now_et.hour == 18 and now_et.minute < 5:
        logger.info(
            "COMEX market opening warmup window active (Sunday 18:00-18:05 ET). Holding trading to let indicators heat up."
        )
        finish_trading_decision_run(
            db,
            decision_run,
            status="skipped",
            action=ACTION_HOLD,
            reason_code="MARKET_OPEN_WARMUP",
            execution_result={"status": "skipped", "skipped_reason": "market_open_warmup", "trade_id": None},
            notification_result={"sent": False, "skipped_reason": "market_open_warmup"},
        )
        db.commit()
        return

    # 1. Fetch configured auto-trading portfolio
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.name == settings.auto_trading_portfolio_name)
    ).scalar_one_or_none()
    if not portfolio:
        logger.error("Auto-trading portfolio %r not found", settings.auto_trading_portfolio_name)
        record_runtime_heartbeat(
            db,
            component=AUTO_TRADER_COMPONENT,
            status="failing",
            expected_interval_seconds=settings.collector_interval_seconds,
            details={"error": "portfolio_not_found", "portfolio_name": settings.auto_trading_portfolio_name},
        )
        finish_trading_decision_run(
            db,
            decision_run,
            status="failed",
            action=ACTION_HOLD,
            reason_code="PORTFOLIO_NOT_FOUND",
            execution_result={"status": "skipped", "skipped_reason": "portfolio_not_found", "trade_id": None},
            notification_result={"sent": False, "skipped_reason": "portfolio_not_found"},
            error_message=f"Portfolio {settings.auto_trading_portfolio_name!r} not found",
        )
        db.commit()
        return

    # 2. Fetch configured auto-trading asset
    asset = db.execute(select(Asset).where(Asset.symbol == settings.auto_trading_asset_symbol)).scalar_one_or_none()
    if not asset:
        logger.error("Auto-trading asset %r not found", settings.auto_trading_asset_symbol)
        record_runtime_heartbeat(
            db,
            component=AUTO_TRADER_COMPONENT,
            status="failing",
            expected_interval_seconds=settings.collector_interval_seconds,
            details={"error": "asset_not_found", "asset_symbol": settings.auto_trading_asset_symbol},
        )
        finish_trading_decision_run(
            db,
            decision_run,
            status="failed",
            action=ACTION_HOLD,
            reason_code="ASSET_NOT_FOUND",
            execution_result={"status": "skipped", "skipped_reason": "asset_not_found", "trade_id": None},
            notification_result={"sent": False, "skipped_reason": "asset_not_found"},
            error_message=f"Asset {settings.auto_trading_asset_symbol!r} not found",
        )
        db.commit()
        return

    requested_strategy = settings.strategy_name or "strategy_v2"
    resolved_policy = resolve_strategy_policy(db, requested_strategy)
    timeframe_contexts = get_strategy_timeframe_contexts(db, asset.symbol, strategy_name=requested_strategy)
    daily_context = timeframe_contexts["1d"]
    hourly_context = timeframe_contexts["1h"]
    execution_context = timeframe_contexts["5m"]
    strategy_readiness_flags = evaluate_timeframe_guardrails(timeframe_contexts, ref_dt=datetime.now(UTC))
    source_divergence = evaluate_source_divergence(db, policy=resolved_policy)
    source_divergence_payload = to_jsonable(source_divergence.to_dict())
    if source_divergence.blocked and SOURCE_DIVERGENCE_BLOCK not in strategy_readiness_flags:
        strategy_readiness_flags.append(SOURCE_DIVERGENCE_BLOCK)

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
        finish_trading_decision_run(
            db,
            decision_run,
            status="failed",
            action=ACTION_HOLD,
            reason_code="PRICE_SNAPSHOT_MISSING",
            source_health=source_health_snapshot(db),
            indicator_readiness=summarize_timeframe_inputs(timeframe_contexts),
            execution_result={"status": "skipped", "skipped_reason": "price_snapshot_missing", "trade_id": None},
            notification_result={"sent": False, "skipped_reason": "price_snapshot_missing"},
            error_message="PriceSnapshot not found for strategy execution.",
        )
        db.commit()
        return

    # Get position status
    current_position = calculate_position(db, portfolio.id, asset.id)
    has_open_position = current_position.quantity > 0

    # Retrieve latest configured sentiment memory event from db
    latest_event = db.execute(
        select(AgentMemoryEvent)
        .where(AgentMemoryEvent.agent_name == settings.auto_trading_sentiment_agent_name)
        .order_by(AgentMemoryEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    news_sentiment = "NEUTRAL"
    if latest_event and latest_event.value_json:
        news_sentiment = latest_event.value_json.get("sentiment", "NEUTRAL")

    active_strategy = requested_strategy
    decision_context = DecisionContext(
        requested_strategy=requested_strategy,
        active_strategy=active_strategy,
        portfolio=portfolio,
        asset=asset,
        latest_snapshot=latest_snapshot,
        latest_indicator=latest_indicator,
        daily_context=daily_context,
        hourly_context=hourly_context,
        execution_context=execution_context,
        timeframe_contexts=timeframe_contexts,
        readiness_block_flags=strategy_readiness_flags,
        source_divergence=source_divergence_payload,
        has_open_position=has_open_position,
        news_sentiment=news_sentiment,
        latest_event=latest_event,
    )

    resolution = await _resolve_strategy_resolution(db, decision_context)
    action = resolution.action
    reason_code = resolution.reason_code
    details = dict(resolution.details)

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
    resolved_strategy = resolution.resolved_strategy
    decision_envelope = build_decision_envelope(
        mode=settings.auto_trading_mode,
        asset_symbol=asset.symbol,
        requested_strategy=requested_strategy,
        resolved_strategy=resolved_strategy,
        candidate_action=resolution.candidate_action,
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
    if resolution.is_blocked:
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
        details_json=to_jsonable({**details, "decision_envelope": decision_envelope}),
    )
    db.add(signal)
    db.flush()

    trade = None
    buy_price = latest_snapshot.buy_price if latest_snapshot.buy_price else latest_snapshot.mid_price
    sell_price = latest_snapshot.sell_price if latest_snapshot.sell_price else latest_snapshot.mid_price

    execution_result = ExecutionOutcome(**decision_envelope["execution"])

    # 6. Trade execution via trade intents only.
    if settings.auto_trading_mode == "diagnostic":
        execution_result = ExecutionOutcome(status="skipped", skipped_reason="diagnostic_mode", trade_id=None)
    elif action == ACTION_BUY and not has_open_position:
        intent = TradeIntent(
            portfolio_name=settings.auto_trading_portfolio_name,
            asset_symbol=settings.auto_trading_asset_symbol,
            action=ACTION_BUY,
            confidence=resolution.confidence,
            reason_code=reason_code,
            stop_loss_price=resolution.stop_loss_price,
            take_profit_price=resolution.take_profit_price,
            expected_exit_price=resolution.expected_exit_price,
            metadata={
                "signal_id": signal.id,
                "trading_decision_run_id": decision_run.id,
                "timeframe_policy": details["timeframe_policy"],
            },
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
            execution_result = ExecutionOutcome(
                status="executed" if trade.action == "paper_buy" else "blocked",
                skipped_reason=None if trade.action == "paper_buy" else trade.risk_decision.reason_code,
                trade_id=trade.id,
            )
        except Exception:
            logger.exception("Failed to execute auto trader BUY intent")
            execution_result = ExecutionOutcome(status="failed", skipped_reason="execution_exception", trade_id=None)
        finally:
            db.commit = original_commit

    elif settings.auto_trading_mode == "paper" and action == ACTION_SELL and has_open_position:
        intent = TradeIntent(
            portfolio_name=settings.auto_trading_portfolio_name,
            asset_symbol=settings.auto_trading_asset_symbol,
            action=ACTION_SELL,
            confidence=resolution.confidence,
            reason_code=reason_code,
            metadata={
                "signal_id": signal.id,
                "trading_decision_run_id": decision_run.id,
                "timeframe_policy": details["timeframe_policy"],
            },
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
            execution_result = ExecutionOutcome(
                status="executed" if trade.action == "paper_sell" else "blocked",
                skipped_reason=None if trade.action == "paper_sell" else trade.risk_decision.reason_code,
                trade_id=trade.id,
            )
        except Exception:
            logger.exception("Failed to execute auto trader SELL intent")
            execution_result = ExecutionOutcome(status="failed", skipped_reason="execution_exception", trade_id=None)
        finally:
            db.commit = original_commit
    else:
        skipped_reason = "not_actionable"
        if action == ACTION_BUY and has_open_position:
            skipped_reason = "position_already_open"
        elif action == ACTION_SELL and not has_open_position:
            skipped_reason = "no_open_position"
        elif reason_code == BLOCKED_CONFIG_INVALID:
            skipped_reason = "config_invalid"
        execution_result = ExecutionOutcome(status="skipped", skipped_reason=skipped_reason, trade_id=None)

    # 7. Extract notification data prior to commit/close to avoid DetachedInstanceError
    notification_data = {
        "action": trade.action if trade else ("blocked" if reason_code in BLOCKED_REASON_CODES else action),
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
        "reason_code": reason_code,
        "readiness_block_flags": strategy_readiness_flags,
        "timeframe_inputs": details.get("timeframe_inputs") or summarize_timeframe_inputs(timeframe_contexts),
        "timeframe_indicators": details.get("timeframe_indicators")
        or build_timeframe_indicator_summary(timeframe_contexts),
        "notification_kind": "readiness_block"
        if reason_code in READINESS_BLOCK_REASONS or strategy_readiness_flags
        else "trade_report",
    }

    if (
        active_strategy == "blended"
        and resolution.exit_metadata
        and resolution.exit_metadata.get("strategy_votes")
        and resolution.exit_metadata.get("arbiter_decision")
    ):
        meta = resolution.exit_metadata or {}
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
        category=_notification_category(notification_data, reason_code),
    )
    should_notify = notification_decision["sent"]
    record_notification_audit(
        db,
        signal=signal,
        asset_symbol=asset.symbol,
        strategy_name=active_strategy,
        notification_action=notification_data["action"],
        decision=notification_decision,
        details={"mode": settings.auto_trading_mode},
    )

    refreshed_details = dict(signal.details_json or {})
    refreshed_envelope = dict(refreshed_details.get("decision_envelope") or {})
    refreshed_envelope["execution"] = execution_result.as_dict()
    refreshed_envelope["notification"] = notification_decision
    if trade and trade.risk_decision:
        refreshed_envelope["risk_preflight"] = {
            "decision": trade.risk_decision.decision,
            "reason_code": trade.risk_decision.reason_code,
            "risk_level": trade.risk_decision.risk_level,
        }
    refreshed_details["decision_envelope"] = refreshed_envelope
    signal.details_json = refreshed_details
    source_health = source_health_snapshot(db)
    source_health["source_divergence"] = source_divergence_payload
    finish_trading_decision_run(
        db,
        decision_run,
        status="completed",
        action=action,
        reason_code=reason_code,
        signal_id=signal.id,
        source_health=source_health,
        indicator_readiness=summarize_timeframe_inputs(timeframe_contexts),
        execution_result=execution_result.as_dict(),
        notification_result=notification_decision,
        details={
            "requested_strategy": requested_strategy,
            "resolved_strategy": resolved_strategy,
            "candidate_action": resolution.candidate_action,
            "readiness_block_flags": strategy_readiness_flags,
            "filter_reason": filter_reason,
            "policy": resolved_policy.to_dict(),
        },
    )

    # Commit transactions
    db.commit()

    # 8. Send Telegram message
    is_silent = False
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
    category: str | None = None,
) -> dict:
    cooldown_seconds = cooldown_minutes * 60
    category = category or ("trade" if notification_action != "HOLD" else "block_change")
    if category in {"trade", "critical"}:
        return NotificationDecision(sent=True, skipped_reason=None, cooldown_seconds=cooldown_seconds).as_dict()
    if category == "hourly_digest":
        cooldown_seconds = 3600
        notification_action = "hourly_digest"
    if notification_action != "HOLD" and notification_action != "hourly_digest":
        return NotificationDecision(sent=True, skipped_reason=None, cooldown_seconds=cooldown_seconds).as_dict()
    if cooldown_seconds <= 0:
        return NotificationDecision(sent=True, skipped_reason=None, cooldown_seconds=cooldown_seconds).as_dict()

    current_time = signal.observed_at
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    cutoff_time = current_time.timestamp() - cooldown_seconds

    previous_audits = (
        db.execute(
            select(NotificationAudit)
            .where(
                NotificationAudit.asset_symbol == asset_symbol,
                NotificationAudit.strategy_name == strategy_name,
                NotificationAudit.notification_action == notification_action,
                NotificationAudit.reason_code == signal.reason_code,
                NotificationAudit.sent.is_(True),
            )
            .order_by(NotificationAudit.observed_at.desc(), NotificationAudit.id.desc())
            .limit(25)
        )
        .scalars()
        .all()
    )

    for audit in previous_audits:
        previous_time = audit.observed_at
        if previous_time.tzinfo is None:
            previous_time = previous_time.replace(tzinfo=UTC)
        if previous_time.timestamp() > cutoff_time:
            return NotificationDecision(
                sent=False,
                skipped_reason="hourly_digest_cooldown" if category == "hourly_digest" else "hold_cooldown",
                cooldown_seconds=cooldown_seconds,
            ).as_dict()

    return NotificationDecision(sent=True, skipped_reason=None, cooldown_seconds=cooldown_seconds).as_dict()


def _notification_category(notification_data: dict, reason_code: str) -> str:
    if notification_data.get("action") in {"paper_buy", "paper_sell", "BUY", "SELL"}:
        return "trade"
    if reason_code in {
        SOURCE_DIVERGENCE_BLOCK,
        "DAILY_BAR_DELAYED",
        "ENTRY_TIMEFRAME_STALE",
        "EXECUTION_TIMEFRAME_STALE",
        BLOCKED_CONFIG_INVALID,
    }:
        return "critical"
    return "block_change"


def record_notification_audit(
    db: Session,
    *,
    signal: Signal,
    asset_symbol: str,
    strategy_name: str,
    notification_action: str,
    decision: dict,
    details: dict | None = None,
) -> NotificationAudit:
    audit = NotificationAudit(
        signal_id=signal.id,
        asset_symbol=asset_symbol,
        strategy_name=strategy_name,
        notification_action=notification_action,
        reason_code=signal.reason_code,
        sent=bool(decision["sent"]),
        skipped_reason=decision.get("skipped_reason"),
        cooldown_seconds=int(decision.get("cooldown_seconds") or 0),
        observed_at=signal.observed_at,
        details_json=details or {},
    )
    db.add(audit)
    db.flush()
    return audit


def get_strategy_timeframe_contexts(db: Session, asset_symbol: str, *, strategy_name: str | None = None) -> dict:
    return {
        timeframe: get_latest_indicator_context(
            db,
            asset_symbol=asset_symbol,
            timeframe=timeframe,
            max_age_minutes=max_age_minutes,
        )
        for timeframe, max_age_minutes in get_strategy_timeframe_policy(db, strategy_name=strategy_name).items()
    }


def evaluate_timeframe_guardrails(timeframe_contexts: dict, ref_dt: datetime | None = None) -> list[str]:
    flags: list[str] = []
    daily_readiness = timeframe_contexts["1d"].readiness
    hourly_readiness = timeframe_contexts["1h"].readiness
    execution_readiness = timeframe_contexts["5m"].readiness

    for readiness in (daily_readiness, hourly_readiness, execution_readiness):
        for reason in readiness.reason_codes:
            if reason in READINESS_BLOCK_REASONS and reason not in flags:
                flags.append(reason)

    if "MARKET_CLOSED" in flags:
        return ["MARKET_CLOSED"]

    if (not daily_readiness.usable or daily_readiness.indicator is None) and not any(
        reason in flags for reason in ("DAILY_BAR_DELAYED", "INSUFFICIENT_HISTORY")
    ):
        flags.append("DAILY_TREND_MISSING")

    if hourly_readiness.status == "stale" and "ENTRY_TIMEFRAME_STALE" not in flags:
        flags.append("ENTRY_TIMEFRAME_STALE")
    elif (
        (not hourly_readiness.usable or hourly_readiness.indicator is None)
        and "ENTRY_TIMEFRAME_STALE" not in flags
        and "INSUFFICIENT_HISTORY" not in flags
    ):
        flags.append("ENTRY_TIMEFRAME_UNUSABLE")

    if execution_readiness.status == "stale" and "EXECUTION_TIMEFRAME_STALE" not in flags:
        flags.append("EXECUTION_TIMEFRAME_STALE")
    elif (
        (not execution_readiness.usable or execution_readiness.indicator is None)
        and "EXECUTION_TIMEFRAME_STALE" not in flags
        and "INSUFFICIENT_HISTORY" not in flags
    ):
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
            "market_state": readiness.market_state,
            "expected_next_bar_at": readiness.expected_next_bar_at.isoformat()
            if readiness.expected_next_bar_at is not None
            else None,
            "freshness_status": readiness.freshness_status,
        }
    return summary
