# ADR-004: Telegram As Adapter Only

## Status

Accepted

## Decision

Telegram is a notification and read client only. The backend core must not depend on Telegram.

## Consequences

Future Telegram code consumes backend services or APIs. Trading, risk, ledger, and backtest behavior cannot live in Telegram handlers.
