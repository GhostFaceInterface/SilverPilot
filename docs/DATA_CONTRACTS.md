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

- Bank silver price primary: Kuveyt Türk public live silver page. Parse only public page content or public browser-loaded finance portal JSON; fallback to failed collector if public discovery or GMS parsing breaks.
- Global XAG/USD resolver: Stooq current CSV quote endpoint is primary; Gold-API free no-auth JSON is an approved fallback; Metals.Dev is an optional free API-key fallback when configured. Stooq historical CSV requires a manually obtained key and stays optional.
- USD/TRY primary: TCMB daily XML. EVDS is optional when a free user key is available.
- Macro/news primary: official Fed RSS and FRED API. FRED is the preferred no-cost macro-series gateway when `FRED_API_KEY` is configured.
- Direct BLS API is deferred. Use FRED-hosted BLS-origin CPI/PPI/labor series first; keep `BLS_API_KEY` optional/backlog.
- Türkiye macro sources matter for TRY execution simulation, bank spread comparison, local risk context, and official tax/rule checks.
- Yahoo Finance and Investing are diagnostic/fallback only due robots, ToS, and dynamic-page risk.

### Free API Key Todo

- Keep optional env names for `FRED_API_KEY`, `BLS_API_KEY`, and `TCMB_EVDS_API_KEY`; keep empty values disabled.
- FRED requires a free user API key and is enabled only when configured.
- Metals.Dev requires a free user API key and is disabled when `METALS_DEV_API_KEY` is empty.
- Gold-API real-time price endpoint requires no API key in the current MVP configuration.
- Direct BLS stays disabled for MVP even though unregistered and registered no-cost access exist.
- TCMB EVDS stays disabled/backlog until a free user key is configured and series choices are approved.
- Never print, log, or commit key values.

Recommended env documentation for future `.env.example` updates:

- `FRED_API_KEY` empty placeholder.
- `BLS_API_KEY` optional/backlog disabled.
- `TCMB_EVDS_API_KEY` optional/backlog disabled.
- `FED_RSS_ENABLED` default true.
- `GLOBAL_XAG_SOURCE_PRIORITY` default `stooq,gold-api,metals-dev`.
- `GOLD_API_XAG_USD_ENABLED` default true.
- `METALS_DEV_API_KEY` optional disabled placeholder.
- `TCMB_DAILY_XML_ENABLED` default true.
- `TUIK_ENABLED` default false.

Langfuse env note:

- Current code does not read Langfuse settings yet.
- `.env.example` currently uses `LANGFUSE_HOST`; local user env may use `LANGFUSE_BASE_URL`.
- The LLM gateway phase must pick one canonical env name before implementing Langfuse.

### FRED Macro Contract

FRED observations are pulled through `fred/series/observations` with `file_type=json` unless another format is explicitly needed. The endpoint supports XML, JSON, XLSX, and zipped CSV; missing values such as `.` must be stored as missing, not coerced to zero.

Initial series:

| Series | Class | Source | Frequency | Use |
| --- | --- | --- | --- | --- |
| `CPIAUCSL` | Global-market context | BLS via FRED | Monthly | U.S. inflation context |
| `PPIACO` | Global-market context | BLS via FRED | Monthly | U.S. producer-price pressure |
| `UNRATE` | Global-market context | BLS via FRED | Monthly | U.S. labor-market context |
| `FEDFUNDS` | Global-market context | Federal Reserve via FRED | Monthly | Policy-rate context |
| `DGS10` | Global-market context | Federal Reserve via FRED | Daily | U.S. yield pressure |
| `DTWEXBGS` | Global-market context | Federal Reserve via FRED | Daily | broad USD strength proxy |

### Türkiye Source Contract

- TCMB daily XML: no API key; key USD/TRY execution-context source; daily indicative rate only, so intraday gaps must be marked as such.
- TCMB EVDS: free-key optional/backlog; candidate series include USD/TRY, policy rates, local rates, reserves, expectations, inflation-related indicators, and other official macro context.
- TÜİK data portal: candidate source for CPI/TÜFE, PPI/ÜFE, confidence indicators, unemployment, and other low-frequency local macro context; not required for MVP intraday collectors.
- Resmi Gazete, GİB, and Hazine ve Maliye Bakanlığı: official tax/KMV/BSMV verification sources; not necessarily continuous collectors.

### Source Research Links

- FRED observations API: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- FRED API keys: https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html
- FRED CPI: https://fred.stlouisfed.org/series/CPIAUCSL
- FRED PPI: https://fred.stlouisfed.org/series/PPIACO
- FRED unemployment: https://fred.stlouisfed.org/series/UNRATE
- FRED fed funds: https://fred.stlouisfed.org/series/FEDFUNDS
- FRED 10-year yield: https://fred.stlouisfed.org/series/DGS10
- FRED broad dollar index: https://fred.stlouisfed.org/series/DTWEXBGS
- BLS API limits: https://www.bls.gov/developers/api_faqs.htm
- TCMB daily FX XML FAQ: https://www.tcmb.gov.tr/wps/wcm/connect/bab69efb-d66c-45b5-91c6-1533886acd6e/GenelAg-SSS.pdf
- TCMB EVDS 3 announcement: https://www.tcmb.gov.tr/wps/wcm/connect/tr/tcmb%2Btr/main%2Bmenu/duyurular/basin/2026/duy2026-03
- TÜİK data portal: https://data.tuik.gov.tr/
- Federal Reserve RSS feeds: https://www.federalreserve.gov/feeds/
- Gold-API docs: https://gold-api.com/docs
- Gold-API pricing: https://gold-api.com/pricing
- Metals.Dev docs: https://metals.dev/docs
- Metals.Dev pricing: https://metals.dev/pricing

### Phase 3.1 Collector Outputs

- `kuveyt_public_silver` writes bank silver prices from Kuveyt Türk official public page data when a public GMS finance-portal row can be parsed; discovery/parser failure records a failed collector run.
- `stooq_xag_usd` writes global XAG/USD using Stooq current CSV `Close` as a zero-spread diagnostic/mid price because bid/ask is not provided.
- `tcmb_usd_try` writes daily USD/TRY using the midpoint of TCMB `ForexBuying` and `ForexSelling`.
- All three collectors store raw payload hashes and parser versions.

### Phase 3.5 Global XAG/USD Contract

Provider interface:

- name: `GlobalSilverPriceProvider`
- normalized output: `source`, `symbol`, `price`, `currency`, `unit`, `observed_at`, `fetched_at`, optional `bid`, optional `ask`, `raw_payload_hash`, `parser_version`, and reliability metadata.
- source priority: `GLOBAL_XAG_SOURCE_PRIORITY`.
- freshness: `GLOBAL_XAG_FRESHNESS_MINUTES`; stale provider data fails and writes no price.

Providers:

- `stooq_xag_usd`: source `stooq-xagusd-csv`, parser `stooq-xagusd-csv-v1`, primary public CSV source, configurable timeout/retry/backoff.
- `global_xag_usd`: resolver collector that records the selected provider in `collector_runs.details_json.selected_global_xag_source`.
- `gold_api_xag_usd`: source `gold-api-xag-usd`, parser `gold-api-xag-usd-v1`, approved free no-auth JSON fallback.
- `metals_dev_silver_spot`: source `metals-dev-silver-spot`, parser `metals-dev-silver-spot-v1`, optional free API-key fallback disabled without `METALS_DEV_API_KEY`.

Failure behavior:

- Provider failures use reason codes: `TIMEOUT`, `HTTP_ERROR`, `PARSE_ERROR`, `STALE_DATA`, `DISABLED`, or `NO_PROVIDER_AVAILABLE`.
- Stooq timeout records a failed `stooq_xag_usd` run, then the resolver may continue to an approved fallback.
- A provider failure must not insert `raw_global_prices` or `price_snapshots`.
- The last successful global XAG row is fresh only while both `observed_at` and `fetched_at` remain within the freshness threshold.
- Manual global XAG can be inserted through `POST /collectors/manual-price` with `source_type=global`, but it is visible as manual fallback and must be fresh to help unblock simulation.

### Phase 3.4 Bank Price Contract

Kuveyt official collector:

- collector: `kuveyt_public_silver`
- source: `kuveyt-public-silver-page`
- parser version: `kuveyt-public-finance-portal-v2`
- output table: `raw_bank_prices`
- required fields: XAG asset, user buy price, user sell price, TRY currency, `observed_at`, `fetched_at`, raw payload hash, parser version, compact payload metadata.
- semantics: bank `SellRate` maps to user `buy_price`; bank `BuyRate` maps to user `sell_price`.
- timestamp: source does not provide a quote timestamp; `observed_at` uses `fetched_at`.
- failure behavior: missing public script, missing public finance portal endpoint, missing GMS row, invalid JSON, or inverted spread creates a failed collector run and no fake price.

Manual fallback:

- existing endpoint: `POST /collectors/manual-price`
- accepted source type: `bank`
- output table: `raw_bank_prices`
- parser version: `manual-v1`
- required fields: `buy_price`, `sell_price`, `observed_at`, `source_name`, optional note in payload.
- use: temporary simulation unblocker only.
- health: fresh manual price is degraded/manual fallback; stale or missing manual price cannot unblock future risk decisions.

### Collector Quality Contract

Endpoint: `GET /collectors/quality`

Purpose: compact Phase 3 validation summary for recent collector operation.

Query:

- `window_hours`, default 24.
- `expected_interval_minutes`, default 60.

Output:

- top-level `status`: `empty`, `ok`, or `degraded`.
- expected runs per collector.
- expected runs so far per collector.
- validation window completion flag.
- elapsed validation coverage minutes for the relevant active collector groups.
- per collector/source run count.
- successful and failed runs.
- records seen, inserted, and duplicates.
- failure ratio.
- duplicate ratio.
- missing-run count and missing-run ratio.
- latest status and latest finish timestamp.

Notes:

- This is a validation metric, not a trading signal.
- Missing-run ratio is calculated against elapsed validation coverage, not future time in the selected window.
- `validation_window_complete` uses relevant collector history so a sliding query window does not remain permanently incomplete after older runs age out of the metric window.
- Inactive manual fallback runs are excluded from quality summaries when public/non-manual collector groups exist.
- Different collector frequencies may need different review windows before Phase 4.
- Missing-run ratio is based on the query's expected interval, not provider freshness guarantees.

### Collector Validation Gate Contract

Endpoint: `GET /collectors/validation-gate`

Purpose: machine-readable Phase 4 readiness check without starting the risk engine.

Output:

- `status`: `empty`, `warming_up`, `ready`, `degraded`, or `blocked`.
- `phase4_allowed`: true only when execution-critical sources are fresh enough and the validation window is complete.
- `reasons`/`blocking_reasons`: compact reason codes such as `VALIDATION_WINDOW_INCOMPLETE`, `EXECUTION_CRITICAL_GLOBAL_XAG_NOT_FRESH`, or `EXECUTION_CRITICAL_BANK_PRICE_NOT_FRESH`.
- `degraded_reasons`: non-blocking quality/context issues.
- `execution_critical_status`: aggregate state for Kuveyt bank silver, global XAG/USD, and USD/TRY.
- `context_status`: aggregate state for Fed RSS and FRED macro.
- `source_reliability`: recent per-source success/failure/missing summary.
- `stooq_xag_usd_timeout_count`: recent Stooq timeout count in the selected window.
- `selected_global_xag_source`: latest fresh global XAG source when available.
- window and expected-run fields matching `/collectors/quality`.

Policy:

- Missing/stale bank silver, global XAG/USD, or USD/TRY blocks Phase 4.
- Fed RSS and FRED macro failures degrade readiness but do not block Phase 4 by themselves.
- Stooq failure does not block Phase 4 when an approved fallback global XAG source is fresh.

### Paper Trade Risk Contract

Endpoint: `POST /paper-trades`

Purpose: create paper-only trade audit records after deterministic risk evaluation.

Response additions:

- `request.expected_exit_price`: optional paper-buy target price used only for deterministic expected-gain checks.
- `trade.risk_decision_id`: required for every persisted paper-trade record.
- `risk_decision.id`: persisted risk decision id.
- `risk_decision.decision`: `allow`, `hold`, or `blocked`.
- `risk_decision.reason_code`: compact reason such as `RISK_CHECK_PASSED`, `SPREAD_TOO_HIGH`, `VOLATILITY_TOO_HIGH`, `DAILY_LOSS_LIMIT_REACHED`, `WEEKLY_LOSS_LIMIT_REACHED`, `FOMO_RISK`, `EXPECTED_GAIN_BELOW_COST`, `MISSING_DATA`, `STALE_DATA`, `INSUFFICIENT_CASH`, or `POSITION_LIMIT_REACHED`.
- `risk_decision.risk_level`: current severity label.
- `risk_decision.confidence`: deterministic confidence, currently `1.0000`.
- `risk_decision.details`: compact machine-readable context; do not place secrets or raw payloads here.

Policy:

- Paper buy/sell cannot bypass the risk engine.
- Policy-blocked buy/sell attempts are persisted as `paper_trades.action=blocked` with the risk decision attached and no portfolio balance mutation.
- Missing/stale execution-critical data blocks buy/sell actions.
- Volatility, realized-loss, FOMO, and optional expected-gain blocks use compact `risk_decision.details` and do not require LLM output.
- Hold and user-blocked audit records do not require market data freshness but still receive a risk decision.

Endpoint: `GET /risk/status`

Purpose: read-only threshold tuning and policy diagnostics for Phase 4.

Response:

- `thresholds`: current deterministic risk thresholds from configuration.
- `current_metrics`: runtime 24-hour/7-day global XAG/USD volatility, FOMO rise, and realized paper loss metrics.
- `would_block_now`: market/history-based block diagnostics such as `VOLATILITY_TOO_HIGH`, `FOMO_RISK`, `DAILY_LOSS_LIMIT_REACHED`, or `WEEKLY_LOSS_LIMIT_REACHED`.
- `recent_decisions`: 24-hour grouped risk decision counts by `decision` and `reason_code`.
- `global_xag_diagnostics`: 24-hour and 7-day global XAG sample counts, latest source/price, min/max price, and per-source sample summaries used to explain volatility tuning.

Policy:

- This endpoint is observational only; it does not create trades or override risk policy.
- Request-specific checks such as spread, expected exit, cash, and position remain enforced by `POST /paper-trades`.
- Global XAG diagnostics are tuning metadata only; they do not select sources or override the collector validation gate.

### Phase 3.2 Fed RSS Output

- `fed_rss` reads the official Federal Reserve monetary policy RSS feed by default.
- Output table: `raw_news`.
- Duplicate guard: one row per `source` and `url`.
- Required fields: title, URL, published timestamp when available, fetched timestamp, raw payload hash, parser version, and compact payload metadata.
- Parser behavior: missing channel/items or missing title/URL creates collector failure; fake news rows are never generated.
- Default source: `federal-reserve-rss`.
- Default parser version: `fed-rss-v1`.

### Phase 3.3 FRED Macro Output

- `fred_macro` reads configured FRED series through the no-cost FRED API key.
- Output table: `raw_events`.
- Event type: `fred_macro_observation`.
- Default source: `fred-api`.
- Default parser version: `fred-observations-v1`.
- Default series: `CPIAUCSL`, `PPIACO`, `UNRATE`, `FEDFUNDS`, `DGS10`, `DTWEXBGS`.
- Required fields: series ID, observation date, value, fetched timestamp, raw payload hash, parser version, realtime start/end when present, and compact metadata.
- Parser behavior: FRED missing values such as `.` are skipped; all-missing or empty responses create a failed collector run.
- Duplicate behavior: exact repeated observations are counted as duplicates, not reinserted.
- Direct BLS stays disabled; BLS-origin CPI/PPI/labor context is pulled through FRED first.

### Runtime Memory Event Contract

Phase 6.5 runtime memory tables store compact operational facts, not raw collector data.

`agent_memory_events` minimum fields:

- `id`
- `event_type`
- `source`
- `agent_name`
- `severity`
- `summary`
- `reason_codes`
- `tags`
- `related_record_type`
- `related_record_id`
- `occurred_at`
- `created_at`
- `metadata_json`
- `redaction_status`

Allowed initial event types:

- `collector_failure`
- `collector_recovered`
- `source_stale`
- `source_reliability_changed`
- `risk_decision`
- `risk_policy_override`
- `agent_disagreement`
- `news_market_link`
- `postmortem`
- `model_or_strategy_note`

Memory exclusions:

- raw price snapshots.
- raw HTML payloads.
- full news dumps.
- full LLM traces.
- secrets, API keys, SSH details, bank details, and `.env` values.

Planned runtime tables:

- paper trades.
- portfolio snapshots.
- risk decisions.
- agent outputs.
- daily reports.
- LLM usage logs.
- backtest results.
- ML dataset versions.
- `agent_memory_events`.
- `source_reliability_daily`.
- `decision_memory`.
- optional `memory_facts`.
- optional `memory_relations`.
- `postmortems`.

Validation rules:

- Duplicate source rows must be rejected or marked.
- Collector failure must be visible in `collector_runs`.
- Raw rows are not deleted during normal operation.
- Public pages must have a configured minimum polling interval.
- Parallel or aggressive requests to the same public page are forbidden.
