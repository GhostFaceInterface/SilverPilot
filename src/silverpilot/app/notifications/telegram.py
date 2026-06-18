from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from urllib import parse, request

from silverpilot.app.api.schemas import (
    AccountResponse,
    BacktestRunResponse,
    HealthResponse,
    MarketRegimeSnapshotResponse,
    PaperTradeResponse,
    PriceQuoteResponse,
    WalletResponse,
)
from silverpilot.app.core.settings import Settings

TelegramDeliveryStatus = Literal["sent", "skipped", "failed"]


@dataclass(frozen=True)
class TelegramMessage:
    text: str
    chat_id: str | None = None
    disable_web_page_preview: bool = True


@dataclass(frozen=True)
class TelegramDeliveryResult:
    status: TelegramDeliveryStatus
    reason: str


class TelegramTransport(Protocol):
    def send_message(self, *, bot_token: str, message: TelegramMessage, chat_id: str) -> None:
        """Send a message through an injected transport."""


class HttpTelegramTransport:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")

    def send_message(self, *, bot_token: str, message: TelegramMessage, chat_id: str) -> None:
        payload = parse.urlencode(
            {
                "chat_id": chat_id,
                "text": message.text,
                "disable_web_page_preview": str(message.disable_web_page_preview).lower(),
            }
        ).encode("utf-8")
        url = f"{self._api_base_url}/bot{bot_token}/sendMessage"
        http_request = request.Request(url, data=payload, method="POST")
        with request.urlopen(http_request, timeout=10):
            return


class TelegramAdapter:
    def __init__(
        self,
        *,
        settings: Settings,
        transport: TelegramTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport or HttpTelegramTransport(settings.telegram_api_base_url)

    def send(self, message: TelegramMessage) -> TelegramDeliveryResult:
        if not self._settings.telegram_enabled:
            return TelegramDeliveryResult(status="skipped", reason="telegram_disabled")
        if not self._settings.telegram_bot_token:
            return TelegramDeliveryResult(status="skipped", reason="telegram_token_missing")

        chat_id = message.chat_id or self._settings.telegram_default_chat_id
        if not chat_id:
            return TelegramDeliveryResult(status="skipped", reason="telegram_chat_missing")

        try:
            self._transport.send_message(
                bot_token=self._settings.telegram_bot_token,
                message=message,
                chat_id=chat_id,
            )
        except Exception:
            return TelegramDeliveryResult(status="failed", reason="telegram_send_failed")

        return TelegramDeliveryResult(status="sent", reason="telegram_sent")


class NotificationService:
    def __init__(self, telegram_adapter: TelegramAdapter | None = None) -> None:
        self._telegram_adapter = telegram_adapter

    def notify_telegram(self, message: TelegramMessage) -> TelegramDeliveryResult:
        if self._telegram_adapter is None:
            return TelegramDeliveryResult(status="skipped", reason="telegram_adapter_missing")
        return self._telegram_adapter.send(message)


class TelegramCommandFormatter:
    def format_wallets(self, account: AccountResponse, wallets: list[WalletResponse]) -> str:
        wallet_lines = [
            (
                f"- {wallet.currency_code}: available {self._money(wallet.available_amount)}, "
                f"reserved {self._money(wallet.reserved_amount)}"
            )
            for wallet in wallets
        ]
        return "\n".join(
            [
                f"Wallet: {account.name}",
                f"Account status: {account.status}",
                f"Base currency: {account.base_currency_code}",
                *wallet_lines,
            ]
        )

    def format_latest_price(self, price: PriceQuoteResponse) -> str:
        return "\n".join(
            [
                "Latest bank price",
                f"Bank instrument: {price.bank_instrument_id}",
                f"Buy: {self._money(price.bank_buy_price)}",
                f"Sell: {self._money(price.bank_sell_price)}",
                f"Freshness: {price.freshness_status}",
                f"Observed at: {price.observed_at.isoformat()}",
            ]
        )

    def format_latest_regime(self, regime: MarketRegimeSnapshotResponse) -> str:
        return "\n".join(
            [
                "Latest market regime",
                f"Regime: {regime.regime}",
                f"Confidence: {self._decimal(regime.confidence)}",
                f"Instrument: {regime.instrument_type}/{regime.instrument_id}",
                f"Timeframe: {regime.timeframe}",
                f"Source bar end: {regime.source_bar_end_at.isoformat()}",
            ]
        )

    def format_latest_trades(self, trades: list[PaperTradeResponse]) -> str:
        if not trades:
            return "Latest paper trades\nNo trades found."

        trade_lines = [
            (
                f"- {trade.side} {self._decimal(trade.quantity)} at "
                f"{self._money(trade.execution_price)}; net {self._money(trade.net_cash_amount)}; "
                f"pnl {self._money(trade.realized_pnl)}"
            )
            for trade in trades
        ]
        return "\n".join(["Latest paper trades", *trade_lines])

    def format_backtest(self, backtest: BacktestRunResponse) -> str:
        trade_count = backtest.trade_count if backtest.trade_count is not None else "n/a"
        completed_at = backtest.completed_at.isoformat() if backtest.completed_at else "n/a"
        return "\n".join(
            [
                "Backtest report",
                f"Status: {backtest.status}",
                f"PnL after costs: {self._optional_decimal(backtest.pnl_after_costs)}",
                f"Trade count: {trade_count}",
                f"Max drawdown: {self._optional_decimal(backtest.max_drawdown)}",
                f"Completed at: {completed_at}",
            ]
        )

    def format_system_health(self, health: HealthResponse) -> str:
        return "\n".join(["System health", f"App: {health.app}", f"Status: {health.status}"])

    def _optional_decimal(self, value: Decimal | None) -> str:
        return self._decimal(value) if value is not None else "n/a"

    def _money(self, value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.00000001'))}"

    def _decimal(self, value: Decimal) -> str:
        return format(value.normalize(), "f")
