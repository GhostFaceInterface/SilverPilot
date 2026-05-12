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

## Development Memory vs Runtime Memory

Development memory is markdown:

- `memory-bank/`
- `docs/`
- `agents/`

Runtime memory is the database:

- price history.
- paper trades.
- portfolio snapshots.
- agent outputs.
- daily reports.
- LLM usage logs.
- backtest results.
- ML dataset versions.

Do not put runtime records into markdown.

## Documentation Pattern

Each concept has one canonical home. Other files may link to it but should not restate it in full.

## LLM Independence Pattern

The system must keep working when LLM APIs are unavailable:

- collect prices.
- calculate portfolio state.
- run risk rules.
- allow or block paper trades.
- show dashboard state.

LLM agents add analysis and reporting, not core availability.
