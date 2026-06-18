# Phase 12: News/Hermes Risk Module

## ROADMAP Objective

Add structured event-risk context. Hermes/news may classify events and produce
risk context, but it must not trade directly or bypass RiskManager.

## Current Evidence

- `src/silverpilot/app/news/service.py` defines `NewsSourceDefinition`,
  `NewsEventPayload`, `HermesRiskPolicy`, `EventRiskRule`,
  `NewsInterpreter`, and `NewsRiskRepository`.
- `src/silverpilot/app/db/models.py` adds `NewsSourceModel`,
  `NewsEventModel`, and `EventRiskSnapshotModel`.
- `migrations/versions/20260618_0009_news_event_risk.py` creates the Phase 12
  tables and constraints.
- `src/silverpilot/app/risks/service.py` adds optional `EventRiskContext` and
  applies event-risk veto, no-trade, and reduction only while evaluating a
  pending trade intent.
- `tests/test_news_phase12.py`, `tests/test_risks.py`, and
  `tests/test_database_schema.py` cover the new behavior.

## Required Interfaces And Schema

- `news_sources`: source registry with category, reliability score, source
  policy, status, and unique source code.
- `news_events`: normalized news record with source event time, provider
  reported time, published/fetched timestamps, title, summary, affected assets,
  event type, and source-scoped content hash.
- `event_risk_snapshots`: Hermes JSON payload with event type, affected assets,
  direction bias, confidence, time horizon, risk level, reasoning, action
  recommendation, interpretation time, and expiry.
- `EventRiskContext`: RiskManager input containing snapshot id, action,
  confidence, assets, interpretation/expiry timestamps, and reasoning.

## Data Flow

A collector or fixture registers a `NewsSourceDefinition`, records a
`NewsEventPayload`, and asks `NewsRiskRepository` to interpret it.
`NewsInterpreter` only interprets events that are already available at the
decision timestamp and still inside the configured freshness window. Fresh
events produce a persisted Hermes JSON snapshot. Trading code may pass that
snapshot summary into `RiskContext.event_risk`; RiskManager then decides
whether to reject, reduce, monitor, or ignore it.

## Failure Modes

- Unknown news source: reject event recording with `ValueError`.
- `fetched_at < published_at`: reject normalized event input.
- Interpretation before published/fetched availability: fail closed with
  `ValueError`.
- Stale news: return no event-risk snapshot.
- Stale event-risk context at risk time: ignore with
  `event_risk_status=ignored_stale`.
- Low-confidence event-risk context: ignore with
  `event_risk_status=ignored_low_confidence`.
- `veto` and `no_trade`: reject only through RiskManager.
- `reduce_risk`: reduce only the RiskManager-approved cash amount.

## Exact Tests

- `pytest tests/test_news_phase12.py`
- `pytest tests/test_risks.py`
- `pytest tests/test_database_schema.py`
- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

PASS when news/event-risk schema migrates cleanly, stale news is ignored,
lookahead news is rejected, Hermes output is structured JSON, event-risk
snapshot persistence is idempotent, and veto/no-trade/reduction effects happen
only inside persisted RiskManager decisions.

## Out Of Scope

- Live news fetching or scraping.
- LLM prompt orchestration or model calls.
- Direct strategy signals, orders, trades, positions, ledger entries, or broker
  execution from Hermes/news.
- Telegram commands.
- Dashboard UI.
- ML experiments.
- Real-money execution.
