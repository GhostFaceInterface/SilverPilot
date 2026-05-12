# System Patterns

## Decision Ownership

The backend owns trade decisions. LLM agents may summarize, explain, classify, or critique, but they do not execute trades.

## Data Flow

```text
collectors
-> raw data
-> normalized snapshots
-> risk engine
-> paper trading engine
-> reports
```

## Documentation Pattern

Each concept has one canonical home. Other files may link to it but should not restate it in full.

