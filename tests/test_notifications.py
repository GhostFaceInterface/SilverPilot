from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

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
from silverpilot.app.notifications import (
    NotificationService,
    TelegramAdapter,
    TelegramCommandFormatter,
    TelegramMessage,
)

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


def test_telegram_formatter_uses_read_only_api_payloads() -> None:
    formatter = TelegramCommandFormatter()
    account = AccountResponse(
        id=uuid4(),
        user_id=uuid4(),
        name="Kuveyt paper account",
        base_currency_id=uuid4(),
        base_currency_code="TRY",
        execution_venue_id=uuid4(),
        execution_venue_code="kuveyt_turk",
        starting_balance=Decimal("1000"),
        status="active",
        created_at=NOW,
    )
    wallet = WalletResponse(
        id=uuid4(),
        account_id=account.id,
        currency_id=uuid4(),
        currency_code="TRY",
        available_amount=Decimal("1000"),
        reserved_amount=Decimal("0"),
        created_at=NOW,
    )
    price = PriceQuoteResponse(
        id=uuid4(),
        bank_instrument_id=uuid4(),
        bank_buy_price=Decimal("50"),
        bank_sell_price=Decimal("51"),
        observed_at=NOW,
        fetched_at=NOW,
        source="kuveyt_turk_finance_portal",
        freshness_status="fresh",
    )
    regime = MarketRegimeSnapshotResponse(
        id=uuid4(),
        instrument_type="reference",
        instrument_id=uuid4(),
        source="fixture",
        timeframe="1h",
        regime="trend_up",
        confidence=Decimal("0.9000"),
        evidence={"candidate_regime": "trend_up"},
        config_version="rule-v1",
        starts_at=NOW,
        confirmed_at=NOW,
        source_bar_end_at=NOW,
    )
    trade = _trade(account.id)
    backtest = BacktestRunResponse(
        id=uuid4(),
        dataset_snapshot_id=uuid4(),
        account_id=account.id,
        strategy_id=uuid4(),
        config_hash="a" * 64,
        status="completed",
        started_at=NOW,
        completed_at=NOW,
        pnl_after_costs=Decimal("42"),
        trade_count=1,
        max_drawdown=Decimal("0.01000000"),
        report={"data_hash": "b" * 64},
    )

    wallet_text = formatter.format_wallets(account, [wallet])
    price_text = formatter.format_latest_price(price)
    regime_text = formatter.format_latest_regime(regime)
    trades_text = formatter.format_latest_trades([trade])
    backtest_text = formatter.format_backtest(backtest)
    health_text = formatter.format_system_health(HealthResponse(status="ok", app="SilverPilot"))

    assert "Wallet: Kuveyt paper account" in wallet_text
    assert "TRY: available 1000.00000000" in wallet_text
    assert "Sell: 51.00000000" in price_text
    assert "Regime: trend_up" in regime_text
    assert "buy 10 at 50.00000000" in trades_text
    assert "PnL after costs: 42" in backtest_text
    assert health_text == "System health\nApp: SilverPilot\nStatus: ok"


def test_disabled_telegram_adapter_skips_without_calling_transport() -> None:
    transport = _RecordingTransport()
    adapter = TelegramAdapter(settings=Settings(telegram_enabled=False), transport=transport)

    result = adapter.send(TelegramMessage(text="hello", chat_id="chat-1"))

    assert result.status == "skipped"
    assert result.reason == "telegram_disabled"
    assert transport.calls == []


def test_enabled_telegram_adapter_uses_injected_transport_without_exposing_token() -> None:
    transport = _RecordingTransport()
    adapter = TelegramAdapter(
        settings=Settings(
            telegram_enabled=True,
            telegram_bot_token="secret-token",
            telegram_default_chat_id="chat-default",
        ),
        transport=transport,
    )

    result = adapter.send(TelegramMessage(text="hello"))

    assert result.status == "sent"
    assert result.reason == "telegram_sent"
    assert transport.calls == [("secret-token", "chat-default", "hello")]
    assert "secret-token" not in result.reason


def test_notification_service_is_optional_when_telegram_is_not_configured() -> None:
    service = NotificationService()

    result = service.notify_telegram(TelegramMessage(text="hello"))

    assert result.status == "skipped"
    assert result.reason == "telegram_adapter_missing"


def _trade(account_id: UUID) -> PaperTradeResponse:
    return PaperTradeResponse(
        id=uuid4(),
        order_id=uuid4(),
        account_id=account_id,
        execution_instrument_id=uuid4(),
        bank_instrument_id=uuid4(),
        quote_id=uuid4(),
        side="buy",
        quantity=Decimal("10"),
        execution_price=Decimal("50"),
        gross_cash_amount=Decimal("500"),
        fees=Decimal("1"),
        taxes=Decimal("0"),
        spread_cost=Decimal("0"),
        net_cash_amount=Decimal("501"),
        realized_pnl=Decimal("0"),
        executed_at=NOW,
    )


class _RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send_message(self, *, bot_token: str, message: TelegramMessage, chat_id: str) -> None:
        self.calls.append((bot_token, chat_id, message.text))
