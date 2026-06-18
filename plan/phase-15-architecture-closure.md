# Phase 15: Roadmap-Code Closure Audit

`ROADMAP.md` remains the canonical product roadmap. This handoff classifies the
post-Phase-14 gap between the implemented codebase and later roadmap language so
Phase 0-14 can be closed without silently claiming future hardening work.

## Gate Status

Phase 0-14 is locally verified after the optional-ML mypy fix:

| Check | Observed result |
| --- | --- |
| `ruff check .` | passed |
| `ruff format --check .` | passed |
| `mypy` | passed |
| `pytest` | 143 passed |
| `bash .codex/scripts/verify-docker.sh` | passed |

Remote GitHub Actions is closed for this gate. The previous Phase 14 commit
failed CI on the optional-ML mypy boundary; commit `43d3b2d` pushed the fix and
the `main` CI run passed.

## Implemented Through Phase 14

- Core schema and migrations through `20260618_0010_ml_experiments`.
- Account-bound paper trading with `paper_orders`, `paper_trades`, positions,
  wallets, and append-only ledger entries.
- Existing trade cost columns: `fees`, `taxes`, and `spread_cost`.
- Backtest replay against shared strategy, risk, broker, and ledger services.
- Read-only REST API, Telegram adapter-only notifications, news/event-risk
  integration, account dashboard reporting, and offline ML experiment metadata.
- Phase 14 offline ML lane with deterministic dataset artifacts, split metadata,
  model-family metadata, advisory reports, and no runtime trading authority.

## Existing Concepts With Different Current Names

- `UnitConversionRule` is implemented as `UnitConversionRuleModel` with
  effective date bounds and an index on from/to units plus `effective_from`.
- `UnitConversionService` exists as a `Protocol` in
  `src/silverpilot/app/domain/interfaces.py`, but no concrete service currently
  performs database-backed effective-date lookup.
- Account-bound execution is represented through virtual account instruments,
  execution instruments, bank instruments, risk decisions, paper orders, and
  paper trades. There is no separate `AccountBoundExecutionResolver` service yet.
- `PaperCostModel` currently acts as a simple aggregate/config object consumed
  by paper trading, backtests, and ML labels.

## Deferred To Phase 16

- `CostBreakdown` and `CostModelService` with detailed spread, fee, tax,
  slippage, conversion cost, rounding adjustment, and total-cost output.
- A detailed cost audit field on `paper_trades`, while preserving the existing
  `fees`, `taxes`, and `spread_cost` columns for compatibility.
- A concrete `UnitConversionService` that uses `UnitConversionRuleModel`,
  effective dates, and Decimal-safe conversion.
- `ExecutionPremiumSnapshot` or an equivalent persisted concept.
- `ExecutionPremiumService` that compares reference converted price against
  account-bound bank buy/sell prices only when required FX and unit conversion
  data exists.
- Explicit failure status such as `missing_fx_rate`; do not fabricate converted
  reference prices.
- Terminology cleanup around `QuoteUnit`, `ExecutionUnit`, and `InstrumentUnit`.
  The current schema has `UnitModel`, instrument mappings, execution
  instruments, bank instruments, and reference instruments, but those three
  named abstractions are roadmap language rather than implemented domain types.

## Deferred To Phase 17

- Offline ML productization gate for manifest/data-hash/split/model-family
  invalidation rules beyond the current Phase 14 baseline.
- Optional ML smoke testing under `.[dev,ml]` only.
- Boundary regressions proving API, strategy, risk, paper broker, Telegram,
  scheduler, and collector paths do not import `ml_experiments`.
- A hard rule that ML artifacts do not create trade intents, sizing, vetoes,
  approvals, executions, or model binaries.
- Any runtime ML promotion plan. It remains blocked until offline evidence
  shows meaningful cost-after improvement over the rule-only baseline.

## Deliberately Out Of Scope For This Closure

- Remote VPS deployment or service restarts.
- Real-money execution.
- Mutating remote bank APIs.
- Auth-less SaaS exposure.
- Multi-bank routing or automatic movement of funds between banks.
- Runtime ML inference.

## Architecture Doc Decision

Do not create `docs/ARCHITECTURE.md` in Phase 15. The current durable decisions
are already captured in `docs/adr/`, and the phase handoff plus `ROADMAP.md`
are sufficient for this closure. Reconsider a consolidated architecture doc
only when Phase 16 introduces cost, conversion, and premium services that need
stable cross-module contracts.

## Acceptance For Closure

Phase 15 is complete when:

- the local verification matrix above remains green;
- the optional `sklearn` mypy boundary is committed and GitHub Actions passes;
- `plan/README.md` points to this closure audit;
- Phase 16/17 items remain explicitly deferred rather than described as
  implemented;
- no runtime ML, real-money execution, remote deployment, or cross-bank routing
  behavior is introduced.
