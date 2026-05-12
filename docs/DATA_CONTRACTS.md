# Data Contracts

This file is the canonical place for durable entity and payload contracts. Exact SQLAlchemy models are implemented in Phase 1 and expanded in later phases.

## Global Rules

- Store timestamps in UTC.
- Use append-only raw collector tables.
- Keep raw data separate from normalized data.
- Never store secrets in database rows.
- Track source name and collection run for imported data.

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

Planned raw tables:

- `raw_bank_prices`
- `raw_global_prices`
- `raw_fx_rates`
- `raw_news`
- `raw_events`
- `collector_runs`

Validation rules:

- Duplicate source rows must be rejected or marked.
- Collector failure must be visible in `collector_runs`.
- Raw rows are not deleted during normal operation.

