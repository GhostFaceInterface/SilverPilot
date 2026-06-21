import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from time import sleep
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from silverpilot.app.api.services import ApiQueryService, Pagination
from silverpilot.app.core.settings import Settings, get_settings
from silverpilot.app.db.models import StrategyRunModel, TelegramBotStateModel, VirtualAccountModel
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.notifications.telegram import HttpTelegramTransport, TelegramMessage
from silverpilot.app.runtime.health import SystemHealthService

READ_ONLY_COMMANDS = (
    "/durum",
    "/health",
    "/prices",
    "/portfolio",
    "/trades",
    "/risk",
    "/help",
)


class TelegramBotTransport:
    def __init__(self, api_base_url: str) -> None:
        self._transport = HttpTelegramTransport(api_base_url)

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        return self._transport.get_updates(
            bot_token=bot_token,
            offset=offset,
            timeout_seconds=timeout_seconds,
        )

    def send_message(self, *, bot_token: str, message: TelegramMessage, chat_id: str) -> None:
        self._transport.send_message(bot_token=bot_token, message=message, chat_id=chat_id)


class TelegramBotTransportProtocol(Protocol):
    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[dict[str, object]]: ...

    def send_message(self, *, bot_token: str, message: TelegramMessage, chat_id: str) -> None: ...


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only Telegram bot status worker.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", default=30.0, type=float)
    parser.add_argument("--poll-timeout-seconds", default=20, type=int)
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_db_engine(args.database_url)
    transport = TelegramBotTransport(settings.telegram_api_base_url)
    while True:
        output = _tick(
            engine=engine,
            settings=settings,
            transport=transport,
            poll_timeout_seconds=args.poll_timeout_seconds,
        )
        print(json.dumps(output, sort_keys=True))
        if args.once:
            return 0
        sleep(args.interval_seconds)


def _tick(
    *,
    engine: Engine,
    settings: Settings,
    transport: TelegramBotTransportProtocol | None = None,
    poll_timeout_seconds: int = 0,
) -> dict[str, object]:
    now = datetime.now(UTC)
    processed_updates = 0
    with Session(engine) as session:
        state = _state(session, now)
        if not settings.telegram_enabled or not settings.telegram_bot_token:
            state.status = "disabled"
            state.last_error = None
        else:
            try:
                processed_updates = _poll_updates(
                    session=session,
                    settings=settings,
                    state=state,
                    transport=transport or TelegramBotTransport(settings.telegram_api_base_url),
                    poll_timeout_seconds=poll_timeout_seconds,
                )
            except Exception as exc:
                state.status = "degraded"
                state.last_error = type(exc).__name__
        state.updated_at = now
        session.commit()
        return {
            "bot_name": state.bot_name,
            "status": state.status,
            "last_update_id": state.last_update_id,
            "processed_updates": processed_updates,
            "read_only_commands": list(READ_ONLY_COMMANDS),
        }


def _poll_updates(
    *,
    session: Session,
    settings: Settings,
    state: TelegramBotStateModel,
    transport: TelegramBotTransportProtocol,
    poll_timeout_seconds: int,
) -> int:
    assert settings.telegram_bot_token is not None
    offset = state.last_update_id + 1 if state.last_update_id is not None else None
    updates = transport.get_updates(
        bot_token=settings.telegram_bot_token,
        offset=offset,
        timeout_seconds=poll_timeout_seconds,
    )
    processed = 0
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            state.last_update_id = max(update_id, state.last_update_id or update_id)
        message = update.get("message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        text = message.get("text")
        if chat_id is None or not isinstance(text, str):
            continue
        if not _chat_is_allowed(chat_id=chat_id, settings=settings):
            continue
        response = _render_command(session=session, settings=settings, text=text)
        transport.send_message(
            bot_token=settings.telegram_bot_token,
            message=TelegramMessage(text=response, chat_id=str(chat_id)),
            chat_id=str(chat_id),
        )
        processed += 1
    health = SystemHealthService(session=session, settings=settings).snapshot()
    state.status = "polling" if health.status != "failed" else "degraded"
    state.last_error = None if health.status != "failed" else "system health failed"
    return processed


def _chat_is_allowed(*, chat_id: object, settings: Settings) -> bool:
    return (
        settings.telegram_default_chat_id is None
        or str(chat_id) == settings.telegram_default_chat_id
    )


def _render_command(*, session: Session, settings: Settings, text: str) -> str:
    command = text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
    service = ApiQueryService(session)
    if command in {"/health", "/durum", "/status"}:
        health = SystemHealthService(session=session, settings=settings).snapshot().payload
        warmup = health.get("warmup", {})
        runtime = health.get("runtime", {})
        telegram = health.get("telegram", {})
        raw_runtime_summary = runtime.get("summary", {}) if isinstance(runtime, dict) else {}
        runtime_summary = raw_runtime_summary if isinstance(raw_runtime_summary, dict) else {}
        counts = health.get("counts", {})
        trade_count = counts.get("trades", "n/a") if isinstance(counts, dict) else "n/a"
        latest_strategy = _latest_strategy_line(session)
        indicators = _indicator_line(runtime_summary)
        return "\n".join(
            [
                "SilverPilot durumu",
                f"Sistem: {health.get('status')}",
                f"Runtime: {runtime.get('status') if isinstance(runtime, dict) else 'n/a'}",
                f"Warm-up: {_warmup_line(warmup)}",
                f"Sinyal: {_signal_line(runtime_summary)}",
                f"Rejim: {runtime_summary.get('regime', 'n/a')}",
                f"Indikatorler: {indicators}",
                f"Strateji: {latest_strategy}",
                f"Paper trades: {trade_count}",
                f"Telegram: {telegram.get('status') if isinstance(telegram, dict) else 'n/a'}",
            ]
        )
    if command in {"/prices", "/fiyat", "/fiyatlar"}:
        prices = service.list_latest_prices(Pagination(page=1, page_size=1)).items
        if not prices:
            return "Latest price\nNo bank price found."
        price = prices[0]
        return "\n".join(
            [
                "Latest bank price",
                f"Buy: {price.bank_buy_price}",
                f"Sell: {price.bank_sell_price}",
                f"Freshness: {price.freshness_status}",
                f"Observed: {price.observed_at.isoformat()}",
            ]
        )
    if command in {"/portfolio", "/portfoy"}:
        account_id = _default_account_id(session, settings)
        if account_id is None:
            return "Portfolio\nNo paper account found."
        report = service.get_account_dashboard_report(account_id=account_id)
        if report is None:
            return "Portfolio\nNo dashboard report found."
        return "\n".join(
            [
                f"Portfolio: {report.account.name}",
                (
                    f"Total value: {report.portfolio.total_value} "
                    f"{report.portfolio.base_currency_code}"
                ),
                f"Net PnL: {report.portfolio.net_pnl} {report.portfolio.base_currency_code}",
                f"Health: {report.health.status}",
            ]
        )
    if command in {"/trades", "/islemler", "/işlemler"}:
        trades = service.list_trades(Pagination(page=1, page_size=5)).items
        if not trades:
            return "\n".join(
                [
                    "Latest paper trades",
                    "No trades found.",
                    _latest_strategy_line(session),
                    (
                        "Otomatik paper trade sadece taze referans sinyali, TREND_UP rejimi, "
                        "pullback kosullari ve risk onayi birlikte gelirse acilir."
                    ),
                ]
            )
        lines = ["Latest paper trades"]
        for trade in trades:
            lines.append(
                f"- {trade.side} {trade.quantity} at {trade.execution_price}; "
                f"pnl {trade.realized_pnl}"
            )
        return "\n".join(lines)
    if command == "/risk":
        account_id = _default_account_id(session, settings)
        if account_id is None:
            return "Risk\nNo paper account found."
        report = service.get_account_dashboard_report(account_id=account_id)
        if report is None:
            return "Risk\nNo dashboard report found."
        return "\n".join(
            [
                "Risk",
                f"Pending intents: {report.risk.pending_intent_count}",
                f"Approved: {report.risk.approved_decision_count}",
                f"Reduced: {report.risk.reduced_decision_count}",
                f"Rejected: {report.risk.rejected_decision_count}",
            ]
        )
    return _help_text()


def _latest_strategy_line(session: Session) -> str:
    run = session.scalar(select(StrategyRunModel).order_by(StrategyRunModel.run_at.desc()))
    if run is None:
        return "no strategy run yet"
    raw_reasons = run.evidence.get("reasons", [])
    reasons = raw_reasons if isinstance(raw_reasons, list) else []
    reason_text = ",".join(str(reason) for reason in reasons) if reasons else "none"
    return f"{run.status}; reason={reason_text}; at={run.run_at.isoformat()}"


def _signal_line(runtime_summary: object) -> str:
    if not isinstance(runtime_summary, dict):
        return "n/a"
    source = runtime_summary.get("signal_source")
    timeframe = runtime_summary.get("signal_timeframe")
    bar_end = runtime_summary.get("signal_bar_end_at")
    available = runtime_summary.get("signal_available_at")
    if source is None:
        return "n/a"
    return f"{source} {timeframe}; bar_end={bar_end}; available={available}"


def _indicator_line(runtime_summary: object) -> str:
    if not isinstance(runtime_summary, dict):
        return "n/a"
    indicators = runtime_summary.get("indicators")
    if not isinstance(indicators, dict) or not indicators:
        return "n/a"
    names = ["ema_50", "ema_200", "rsi_14", "atr_14", "adx_14", "bb_width_20"]
    present = [name for name in names if name in indicators]
    return ", ".join(present) if present else "n/a"


def _default_account_id(session: Session, settings: Settings) -> UUID | None:
    if settings.runtime_account_id is not None:
        return settings.runtime_account_id
    return session.scalar(
        select(VirtualAccountModel.id)
        .where(VirtualAccountModel.status == "active")
        .order_by(VirtualAccountModel.created_at.desc(), VirtualAccountModel.id)
    )


def _warmup_line(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    complete = value.get("complete")
    bars = value.get("bars")
    required = value.get("required_bars")
    blocked_by = value.get("blocked_by")
    suffix = f", blocked_by={blocked_by}" if blocked_by else ""
    return f"complete={complete}, bars={bars}/{required}{suffix}"


def _help_text() -> str:
    return "\n".join(
        [
            "SilverPilot read-only commands",
            "/durum - sistem, sinyal, rejim ve strateji ozeti",
            "/health - system runtime status",
            "/prices - latest Kuveyt indicative bank quote",
            "/portfolio - paper account portfolio",
            "/trades - latest paper trades",
            "/risk - latest risk summary",
            "/help - this message",
        ]
    )


def _state(session: Session, now: datetime) -> TelegramBotStateModel:
    state = session.scalar(
        select(TelegramBotStateModel).where(TelegramBotStateModel.bot_name == "silverpilot")
    )
    if state is not None:
        return state
    state = TelegramBotStateModel(
        id=uuid4(),
        bot_name="silverpilot",
        status="disabled",
        created_at=now,
    )
    session.add(state)
    session.flush()
    return state


if __name__ == "__main__":
    raise SystemExit(main())
