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

Runtime memory belongs in PostgreSQL:

- price history.
- paper trades.
- portfolio snapshots.
- risk decisions.
- agent outputs.
- daily reports.
- LLM traces and usage logs.
- backtest results.
- ML dataset versions.

Markdown must not become a storage layer for market data, logs, reports, or agent outputs.

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

Production hardening is Phase 13, not Phase 1.
