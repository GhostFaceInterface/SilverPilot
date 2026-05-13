# Data Contracts

This file is the canonical place for durable entity and payload contracts. Exact SQLAlchemy models are implemented in Phase 1 and expanded in later phases.

## Global Rules

- Store timestamps in UTC.
- Use append-only raw collector tables.
- Keep raw data separate from normalized data.
- Never store secrets in database rows.
- Track source name and collection run for imported data.
- Store runtime records in PostgreSQL, not markdown.
- Keep markdown limited to development memory and durable documentation.
- MVP collectors use free/public sources only; paid market-data APIs remain disabled.
- Free API-key sources are allowed when the key unlocks a no-cost tier only; never store key values in markdown or git.
- Public-page collectors must not require login, captcha/paywall bypass, anti-bot bypass, or private endpoint reverse engineering.
- Store `source`, `observed_at`, `fetched_at`, `raw_payload_hash`, and `parser_version` for collector outputs once the table supports them.
- Parser failure must create a failed collector run; never invent data or silently reuse the last price as fresh.

## Initial Entities

### Asset

- `id`
- `symbol`
- `name`
- `asset_type`
- `is_active`

### PriceSnapshot

- `id`
- `asset_id`
- `source`
- `buy_price`
- `sell_price`
- `mid_price`
- `currency`
- `spread_absolute`
- `spread_percent`
- `observed_at`
- `created_at`

### Portfolio

- `id`
- `name`
- `base_currency`
- `initial_cash`
- `cash_balance`
- `is_real_money`
- `created_at`

`is_real_money` must remain false for this project.

### PaperTrade

- `id`
- `portfolio_id`
- `asset_id`
- `action`
- `quantity`
- `price`
- `gross_amount`
- `fees`
- `taxes`
- `net_amount`
- `risk_decision_id`
- `created_at`

Allowed actions:

- `paper_buy`
- `paper_sell`
- `hold`
- `blocked`

### PortfolioSnapshot

- `id`
- `portfolio_id`
- `cash_balance`
- `asset_quantity`
- `portfolio_value`
- `realized_pnl`
- `unrealized_pnl`
- `observed_at`

### RiskRule

- `id`
- `code`
- `description`
- `severity`
- `is_active`
- `params_json`

### RiskDecision

- `id`
- `decision`
- `reason_code`
- `risk_level`
- `confidence`
- `details_json`
- `created_at`

### Signal

- `id`
- `source`
- `asset_id`
- `signal`
- `confidence`
- `risk_decision_id`
- `created_at`

### Report

- `id`
- `report_type`
- `period_start`
- `period_end`
- `payload_json`
- `created_at`

### AgentRun

- `id`
- `agent_name`
- `model`
- `status`
- `trace_id`
- `input_tokens`
- `output_tokens`
- `cost_estimate`
- `started_at`
- `finished_at`

## Collector Tables

### CollectorRun

- `id`
- `collector_name`
- `source`
- `status`
- `records_seen`
- `records_inserted`
- `duplicates`
- `error_message`
- `started_at`
- `finished_at`
- `details_json`

### Raw Collector Tables

Implemented raw tables:

- `raw_bank_prices`
- `raw_global_prices`
- `raw_fx_rates`
- `raw_news`
- `raw_events`

### Raw Price Tables

Price tables:

- `raw_bank_prices`
- `raw_global_prices`

Shared fields:

- `id`
- `collector_run_id`
- `asset_id`
- `source`
- `buy_price`
- `sell_price`
- `currency`
- `observed_at`
- `fetched_at`
- `raw_payload_hash`
- `parser_version`
- `payload_json`
- `created_at`

Duplicate guard:

- one row per `asset_id`, `source`, and `observed_at`.

### Other Raw Table Minimum Fields

- FX rows keep source, currency pair, rate, observed timestamp, and raw payload.
- News rows keep source, title, URL, publish timestamp, and raw payload.
- Event rows keep source, event type, observed timestamp, and raw payload.

### MVP Free Source Candidates

- Bank silver price primary POC: Kuveyt Türk public live silver page. Parse only public content or public page-loaded data; fallback to failed collector if selectors break.
- Global XAG/USD primary: Stooq current CSV quote endpoint. Stooq historical CSV requires a manually obtained key and stays optional.
- USD/TRY primary: TCMB daily XML. EVDS is optional when a free user key is available.
- Macro/news primary: official Fed RSS, BLS API, and FRED API. BLS registration and FRED keys are acceptable no-cost setup tasks; RSS polling should be low-frequency.
- Yahoo Finance and Investing are diagnostic/fallback only due robots, ToS, and dynamic-page risk.

### Free API Key Todo

- Add optional env names for `BLS_API_KEY` and `FRED_API_KEY`; keep empty values disabled.
- BLS may run without a key at lower quota, but registered free key support should be implemented.
- FRED requires a free user API key; collector stays disabled until the key is configured.
- Never print, log, or commit key values.

### Phase 3.1 Collector Outputs

- `kuveyt_public_silver` writes bank silver prices from the public page POC when visible GMS labels can be parsed; selector failure records a failed collector run.
- `stooq_xag_usd` writes global XAG/USD using Stooq current CSV `Close` as a zero-spread diagnostic/mid price because bid/ask is not provided.
- `tcmb_usd_try` writes daily USD/TRY using the midpoint of TCMB `ForexBuying` and `ForexSelling`.
- All three collectors store raw payload hashes and parser versions.

Planned runtime tables:

- paper trades.
- portfolio snapshots.
- risk decisions.
- agent outputs.
- daily reports.
- LLM usage logs.
- backtest results.
- ML dataset versions.

Validation rules:

- Duplicate source rows must be rejected or marked.
- Collector failure must be visible in `collector_runs`.
- Raw rows are not deleted during normal operation.
- Public pages must have a configured minimum polling interval.
- Parallel or aggressive requests to the same public page are forbidden.
