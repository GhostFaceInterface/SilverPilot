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

## Deployment Shape

Initial VPS deployment should use Docker Compose:

- API container.
- PostgreSQL container or managed PostgreSQL.
- Optional dashboard container.
- Backup job.
- Health checks.

Production hardening is Phase 13, not Phase 1.

