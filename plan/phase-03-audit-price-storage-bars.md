# Phase 3 Audit: Price Storage And Bar Builder

## ROADMAP Objective

Persist quotes and aggregate bars. Deliver collector service, quote tables, and
bar builder with duplicate handling, freshness classification, quote-count bars,
and retention. Do not include strategies.

## Current Evidence

- `src/silverpilot/app/collectors/price_collector.py` implements
  `PriceCollector`, `persist_provider_quote`, quote freshness classification,
  retention pruning, `QuoteBarBuilder`, and bank instrument loading.
- `src/silverpilot/app/collectors/cli.py` provides the
  `silverpilot-collect-kuveyt` entrypoint.
- `src/silverpilot/app/db/models.py` includes `price_quotes` and `market_bars`.
- `tests/test_price_collector.py` covers quote persistence, duplicate handling,
  freshness states, bar building, updates, retention, and CLI behavior.

## Required Interfaces And Schema

- Input: `PriceProvider` and `BankInstrument`.
- Output: append-only `price_quotes` with `source_hash` and `freshness_status`.
- Bar cache: `market_bars` unique by instrument type, instrument id, timeframe,
  and bar start.
- Supported quote price sides: bank buy, bank sell, and mid.

## Data Flow

`PriceCollector` fetches a provider quote, classifies freshness, deduplicates by
bank instrument, observed time, source, and source hash, then persists accepted
quotes. `QuoteBarBuilder` reads persisted fresh quotes for a time window and
upserts deterministic OHLC bars with a quote count.

## Failure Modes

- Persisting duplicate provider payloads as new quote rows.
- Building bars from stale/future quotes by default.
- Building a bar with no quotes.
- Invalid bar windows.
- Incorrect bank buy/sell side selection.
- Retention policy deleting too aggressively or accepting non-positive windows.

## Exact Tests

- `pytest tests/test_price_collector.py`
- Verify duplicate quote handling.
- Verify fresh, stale, and future freshness classification.
- Verify OHLC and quote count for mid, bank buy, and bank sell sides.
- Verify retention cutoff behavior.
- Verify CLI bounded collection behavior.

## Done Gate

Quotes are persisted with freshness status and source hash, duplicate rows are
not inserted, bars are reproducible from accepted quotes, retention is tested,
and no strategy, regime, risk, broker, or backtest behavior exists.

## Out Of Scope

- Always-on scheduler.
- Cold archive storage.
- Strategy or signal generation.
- Multi-bank routing.
- Real execution.
