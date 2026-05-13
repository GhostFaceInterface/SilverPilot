# Architecture

This file is the canonical architecture overview. Phase details live in `docs/ROADMAP.md`; durable decisions live in `docs/DECISIONS.md`.

## Core Principle

SilverPilot is deterministic first. LLM and ML components may assist analysis, but they do not own execution.

```text
No real-money execution.
No bank automation.
No live buy/sell path.
```

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

```text
API layer
-> services
-> repositories / database
-> collectors
-> risk policy
-> paper trading
-> reports
```

Later layers:

```text
LLM gateway
-> structured agent outputs
-> Langfuse traces
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
-> agent explanation
```

The paper-trading engine must not run without a risk decision once Phase 4 exists.

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
- Türkiye local macro data informs TRY execution, bank spread, local risk, and tax/rule context; it is not a primary global silver direction signal.

## Data Impact Classes

- Execution-critical: bank silver buy/sell, spread, USD/TRY or bank FX effect, tax/KMV/BSMV rules.
- Global-market context: XAG/USD, U.S. rates, dollar index, CPI/PPI, Fed RSS.
- Local-macro context: TCMB rates, TRY pressure, Türkiye inflation, local confidence indicators, official rule changes.
- Optional/backlog: direct BLS, TÜİK automated collector, deeper TCMB EVDS series, paid market-data APIs.

## LLM Pattern

- OpenRouter is the first provider gateway.
- LiteLLM is optional when routing, fallback, and budget controls need a proxy.
- Langfuse is required before production agent usage.
- Instructor/Pydantic structured outputs are required for agent responses.
- Free-form LLM output must not drive system decisions.
- Budget guards must block calls after configured limits.
- Core backend behavior must work when LLM providers are down.

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
- Langfuse: LLM trace, cost, latency, and prompt observability.
- Optional future `pgvector`: semantic retrieval inside PostgreSQL only if compact structured queries are not enough.
- Graph memory frameworks: not part of MVP.

Zep/Graphiti are excluded for now because cloud cost and self-host operations are not justified on the current 4 vCPU / 6 GB VPS. Mem0 OSS, Cognee, LightRAG, and Letta remain research-only.

## Deployment Shape

Initial VPS deployment should use Docker Compose:

- API container.
- PostgreSQL container or managed PostgreSQL.
- Optional dashboard container.
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
- Required VPS smoke checks are Compose config, container rebuild, Alembic migration, `/health`, TCMB collector, Stooq collector, and collector health.
- Kuveyt public-page collector remains best-effort during smoke validation because selector failure is an expected safe failure mode.

Production hardening is Phase 13, not Phase 1.
