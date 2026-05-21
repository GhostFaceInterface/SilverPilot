# Architecture

This file is the canonical architecture overview. Phase details live in `docs/ROADMAP.md`; durable decisions live in `docs/DECISIONS.md`.

## Core Principle

SilverPilot is deterministic first. LLM and ML components may assist analysis, but they do not own execution.

```text
No real-money execution.
No bank automation.
No live buy/sell path.
```

OpenClaw is mandatory from the agent phase onward, but it is not part of the deterministic trading core. The backend remains authoritative for collectors, risk policy, paper trading, accounting, and persistence. Backend APIs and approved backend services are the boundary between OpenClaw and the core system.

## Memory Model

Use one canonical memory bank plus short agent-specific spec files.

```text
memory-bank/ = shared project brain
agents/ = small agent role boundaries
docs/ = durable roadmap, architecture, decisions, contracts, policies, and worklog
```

Separate large memory banks per agent are rejected because they create synchronization and duplication risk.

## Development Memory vs Runtime Memory

Development memory is for code-writing agents:

- `memory-bank/`
- `docs/`
- `agents/`

Runtime market/source data belongs in PostgreSQL raw and normalized tables:

- price history.
- paper trades.
- portfolio snapshots.
- risk decisions.
- agent outputs.
- daily reports.
- backtest results.
- ML dataset versions.

Runtime operational memory also belongs in PostgreSQL, but in compact memory-specific tables:

- high-level agent events.
- collector reliability facts.
- source failure patterns.
- decision summaries.
- risk policy overrides.
- agent disagreement records.
- postmortems.
- source trust scores.
- outcome notes.

Langfuse is the home for LLM traces, cost, latency, and prompt observability. Markdown must not become a storage layer for market data, logs, reports, or agent outputs.

## Runtime Layers

1. Deterministic Core

- FastAPI.
- PostgreSQL.
- collectors.
- risk engine.
- paper trading.

2. Visibility Layer

- dashboard.
- health/status endpoints.
- Initial dashboard is a read-only Streamlit app served through the optional Docker Compose `dashboard` profile.

3. LLM/Observability Layer

- OpenRouter.
- Langfuse.
- structured outputs.
- budget guard.

4. Runtime Memory Layer

- PostgreSQL memory tables.
- memory query service.

5. OpenClaw Agent Orchestration Layer

- OpenClaw Gateway/workspace.
- project-local SilverPilot skills.
- agent task routing.
- research/report/critique/audit workflows.

Later layers:

```text
LLM gateway
-> structured agent outputs
-> Langfuse traces
-> OpenClaw orchestration
-> ML dataset automation
-> backtests
-> model registry
```

## Decision Flow

```text
raw data
-> normalized snapshots
-> features
-> rule engine
-> risk engine
-> paper trade decision
-> OpenClaw agent explanation/critique/report
```

The paper-trading engine must not run without a risk decision now that Phase 4 has started. `POST /paper-trades` evaluates deterministic risk before mutating the paper portfolio. Allowed actions update virtual balances, while policy-blocked buy/sell attempts create a `blocked` paper-trade audit row with `risk_decision_id` and do not mutate cash or position. Hold and user-blocked records also receive explicit risk decisions.

## Data Storage Pattern

- Raw collector data is append-only.
- Normalized snapshots are stored separately.
- Derived features are reproducible from source data.
- All event timestamps are stored in UTC.
- Dataset versions are created before ML training.

## MVP Data Source Policy

- Paid market-data APIs are disabled for MVP.
- Official free sources are preferred.
- Free API keys are allowed when the provider does not charge for the required tier; key values stay in local env files only.
- Public pages may be collected only when no login, captcha bypass, paywall bypass, anti-bot bypass, or private endpoint reverse engineering is involved.
- Third-party public pages are fallback or comparison sources unless explicitly approved.
- Public collectors must use polite polling, honest User-Agent headers, selector-failure detection, raw payload hashes, and visible collector failures.
- Robots/ToS uncertainty must be recorded as medium or high source risk.
- FRED is the preferred no-cost macro-series gateway for MVP when `FRED_API_KEY` is configured.
- Direct BLS collection is deferred; BLS-origin CPI/PPI/labor series should come through FRED first when available.
- TCMB daily XML is the primary USD/TRY execution-context source; TCMB EVDS and TÜİK are optional deeper local-macro sources.
- Türkiye local macro data informs USD execution (from local TRY), bank spread, local risk, and tax/rule context; it is not a primary global silver direction signal.
- Kuveyt Türk official public silver page is the primary execution-critical bank silver source when its public browser-loaded finance portal data is available.
- Manual bank-price fallback is a simulation unblocker only; it is not a production collector and must be visible as degraded/manual source context.
- Global XAG/USD uses a provider resolver, not a single source. Stooq current CSV is the primary public source; Gold-API free no-auth JSON is an approved fallback; Metals.Dev is an optional free API-key fallback and is disabled without a key.
- Provider failures record reason codes and never write fake prices or mark the last successful global value as fresh.

## Data Impact Classes

- Execution-critical: bank silver buy/sell, global XAG/USD, USD/TRY or bank FX effect, tax/KMV/BSMV rules.
- Global-market context: U.S. rates, dollar index, CPI/PPI, Fed RSS.
- Local-macro context: TCMB rates, USD/TRY pressure, Türkiye inflation, local confidence indicators, official rule changes.
- Optional/backlog: direct BLS, TÜİK automated collector, deeper TCMB EVDS series, paid market-data APIs.

## Collector Health States

- `healthy`: execution-critical sources are fresh and collectors are fresh.
- `degraded`: core simulation can continue, but some collectors failed/stale or manual fallback is active.
- `blocked`: execution-critical bank silver buy/sell, global XAG/USD, or USD/TRY data is missing.
- `stale`: an execution-critical source exists but exceeded the freshness threshold.
- `empty`: no collector runs exist yet.

Collector quality review uses `/collectors/quality` to summarize recent run counts, failures, duplicates, and missing-run ratio. Missing runs are measured against elapsed validation coverage so a new 24-hour validation run does not count future intervals as already missing, while a sliding query window does not stay permanently incomplete after older runs age out of the metric window. `/collectors/validation-gate` separates execution-critical blockers from context degradation: Kuveyt bank silver, global XAG/USD, and USD/TRY can block Phase 4; Fed RSS and FRED macro failures degrade the output but do not block by themselves. The collector runner supports `COLLECTOR_JOBS` for comma-separated sustained MVP collector batches without starting separate containers per source; the Compose collector profile defaults to the current MVP source batch.

## Risk Engine

Phase 4 uses a deterministic backend risk service before paper-trade persistence. It checks the current execution-critical collector state, request spread, paper cash, paper position, realized loss limits, source-aware global XAG/USD volatility, source-aware rapid-rise FOMO risk, and optional expected exit price. Missing/stale Kuveyt bank silver, global XAG/USD, or USD/TRY blocks buy/sell decisions; context collectors do not block by themselves. Configurable thresholds include `RISK_DATA_STALE_AFTER_MINUTES`, `RISK_MAX_SPREAD_PERCENT`, `RISK_MAX_24H_VOLATILITY_PERCENT`, `RISK_MAX_7D_VOLATILITY_PERCENT`, `RISK_FOMO_LOOKBACK_MINUTES`, `RISK_FOMO_RISE_PERCENT`, `RISK_MAX_DAILY_LOSS_USD`, `RISK_MAX_WEEKLY_LOSS_USD`, and `RISK_MIN_EXPECTED_NET_GAIN_PERCENT`.

`GET /risk/status` exposes the current threshold configuration, runtime metrics used for tuning, per-threshold headroom diagnostics, deterministic `would_block_now` diagnostics, recent 24-hour risk decision counts, and global XAG source/sample/range diagnostics for the 24-hour and 7-day windows. This endpoint is read-only and does not create trades, override policy, or relax execution-critical data requirements. Cross-source range is diagnostic only; block metrics are computed per source and use the highest source-specific range/rise. Phase 5 dashboard visibility should surface this endpoint before any broader threshold tuning; `near_limit` is monitoring context, not an automatic reason to loosen volatility thresholds.

## LLM Pattern

- OpenRouter is the first provider gateway.
- LiteLLM is optional when routing, fallback, and budget controls need a proxy.
- Langfuse is required before production agent usage.
- Instructor/Pydantic structured outputs are required for agent responses.
- Free-form LLM output must not drive system decisions.
- Budget guards must block calls after configured limits.
- Core backend behavior must work when LLM providers are down.
- OpenClaw is the mandatory agent orchestration layer after the LLM gateway and safety boundaries exist.
- OpenClaw must use least-privilege tool access.
- OpenClaw must use project-local SilverPilot skills first.
- Third-party OpenClaw/ClawHub skills require explicit review before use.
- OpenClaw can consume sanitized backend summaries and approved API/service outputs, not production secrets or raw privileged access.
- OpenClaw cannot directly mutate production database state; write operations must go through approved backend APIs or services when such workflows are explicitly implemented.

Initial budget guard targets:

- News Agent: daily max 0.20 USD.
- Report Agent: daily max 0.10 USD.
- Risk Agent: daily max 0.30 USD.
- Audit Agent: weekly max 1.00 USD.

## Runtime Operational Memory

Phase 6.5 adds a lightweight PostgreSQL runtime memory layer before external graph memory is considered.

- `memory-bank/*.md`: development memory for coding agents.
- PostgreSQL raw tables: runtime market/source data and raw payload hashes.
- PostgreSQL runtime memory tables: compressed operational memory for agents.
- backend memory query service: approved context source for OpenClaw agents.
- Langfuse: LLM trace, cost, latency, and prompt observability.
- Optional future `pgvector`: semantic retrieval inside PostgreSQL only if compact structured queries are not enough.
- Graph memory frameworks: not part of MVP.

Zep/Graphiti are excluded for now because cloud cost and self-host operations are not justified on the current 4 vCPU / 6 GB VPS. Mem0 OSS, Cognee, LightRAG, and Letta remain research-only.

OpenClaw agents may read runtime memory only through approved backend memory query services and may write memory only through approved backend memory write services. They must not write arbitrary raw memory, raw payloads, full news dumps, full traces, secrets, SSH details, API keys, or bank details.

## Deployment Shape

Initial VPS deployment should use Docker Compose:

- API container.
- PostgreSQL container or managed PostgreSQL.
- Optional dashboard container through the `dashboard` Compose profile.
- Backup job.
- Health checks.

Deployment target:

- Ubuntu VPS accessed via SSH alias `silverpilot-vps`.
- Container runtime is Docker / Docker Compose.
- Only reverse proxy ports should be public later.
- Database, Redis, and internal services must stay private.

## CI/CD Shape

- GitHub Actions runs backend tests, Docker Compose config validation, and API image build on push and pull request.
- VPS deployment/smoke validation is manual through `workflow_dispatch`.
- The VPS workflow uses repository secrets for host, user, SSH key, and optional known hosts; secrets must not be committed or written to markdown.
- Required VPS smoke checks are Compose config, container rebuild, Alembic migration, `/health`, Kuveyt bank silver, global XAG/USD resolver, TCMB USD/TRY, Fed RSS, FRED macro, collector health, collector quality, and collector validation gate.
- One-shot collector runner commands must exit non-zero when the collector records a failed run, so CI smoke cannot silently pass a failed public-source parser.

Production hardening is Phase 13, not Phase 1.
