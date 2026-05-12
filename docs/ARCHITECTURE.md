# Architecture

## Memory Model

Use one canonical memory bank plus short agent-specific spec files.

```text
memory-bank/ = shared project brain
agents/ = small agent role boundaries
docs/ = durable architecture, decisions, contracts, policies, and worklog
```

## Runtime Model

Initial runtime will be deterministic backend services. LLM and ML layers are added only after data, paper trading, and risk policy are stable.

## Decision Flow

```text
data
-> features
-> rule engine
-> risk engine
-> paper trade decision
-> agent explanation
```

