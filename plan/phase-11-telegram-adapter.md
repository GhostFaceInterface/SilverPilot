# Phase 11: Telegram Adapter

## ROADMAP Objective

Add Telegram as a read/notification client. Telegram may format and send
backend outputs, but it must not own trading decisions or become required for
collectors, strategies, risk decisions, paper execution, ledger correctness, or
backtests.

## Current Evidence

- `src/silverpilot/app/notifications/telegram.py` adds
  `TelegramCommandFormatter`, `TelegramAdapter`, `NotificationService`,
  `TelegramMessage`, `TelegramDeliveryResult`, and transport abstractions.
- `src/silverpilot/app/notifications/__init__.py` exports the notification
  boundary.
- `src/silverpilot/app/core/settings.py` adds disabled-by-default Telegram
  settings.
- `tests/test_notifications.py` verifies formatting, disabled behavior,
  injected transport sends, and optional notification service behavior.

## Required Interfaces And Schema

- `TelegramCommandFormatter` accepts Phase 10 API DTOs:
  - `AccountResponse`
  - `WalletResponse`
  - `PriceQuoteResponse`
  - `MarketRegimeSnapshotResponse`
  - `PaperTradeResponse`
  - `BacktestRunResponse`
  - `HealthResponse`
- `TelegramAdapter.send(message)` returns a delivery result:
  - `sent`
  - `skipped`
  - `failed`
- Telegram settings:
  - `telegram_enabled`
  - `telegram_bot_token`
  - `telegram_default_chat_id`
  - `telegram_api_base_url`

## Data Flow

Backend/API/service-layer outputs are formatted into plain text by
`TelegramCommandFormatter`. `NotificationService` routes messages to an
optional `TelegramAdapter`. The adapter checks whether Telegram is enabled and
configured before using its injected transport. Disabled or missing Telegram
returns a skipped result and does not throw through core services.

## Failure Modes

- Telegram disabled: return `skipped/telegram_disabled`.
- Missing token: return `skipped/telegram_token_missing`.
- Missing chat id: return `skipped/telegram_chat_missing`.
- Missing adapter: return `skipped/telegram_adapter_missing`.
- Transport exception: return `failed/telegram_send_failed` without exposing
  tokens in the delivery result.

## Exact Tests

- `pytest tests/test_notifications.py`
- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

PASS when Telegram formatting uses read-only backend DTOs, notification sending
is disabled by default, no core trading/backtest path imports Telegram, all
sends are transport-injected for tests, and full verification is green.

## Out Of Scope

- Telegram polling or webhooks.
- Telegram-owned trading decisions.
- Authenticated remote command handling.
- Mutating API/trading endpoints.
- Dashboard behavior.
- Hermes, ML, news/event-risk logic.
- Real-money execution.
