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

- Core schema and migrations through `20260618_0010_ml_experiments` at the time
  of the Phase 15 audit.
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
- Account-bound execution is represented through virtual account instruments,
  execution instruments, bank instruments, risk decisions, paper orders, and
  paper trades. `AccountBoundExecutionResolver` is implemented in
  `src/silverpilot/app/risks/service.py`.
- `PaperCostModel` acted as a simple aggregate/config object consumed by paper
  trading, backtests, and ML labels at this audit point.

## Implemented In Phase 16

- `CostBreakdown` and `CostModelService` with detailed spread, fee, tax,
  slippage, conversion cost, rounding adjustment, and total-cost output.
- A detailed cost audit field on `paper_trades`, while preserving the existing
  `fees`, `taxes`, and `spread_cost` columns for compatibility.
- `DatabaseUnitConversionService` that uses `UnitConversionRuleModel`,
  effective dates, and Decimal-safe conversion.
- `ExecutionPremiumSnapshotModel`.
- `ExecutionPremiumService` that compares reference converted price against
  account-bound bank buy/sell prices only when required FX and unit conversion
  data exists.
- Explicit failure status such as `missing_fx_rate`; do not fabricate converted
  reference prices.

## Implemented In Phase 17

- Offline ML productization gate for manifest/data-hash/split/model-family
  invalidation rules beyond the Phase 14 baseline.
- Optional ML smoke testing under `.[dev,ml]` only.
- Boundary regressions proving API, strategy, risk, paper broker, Telegram,
  notification, collector, and backtest runtime paths do not import
  `ml_experiments`.
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
are sufficient for this closure. Phase 16/17 details are captured in
`phase-16-cost-conversion-premium.md` and
`phase-17-ml-productization-boundary.md`.

## Acceptance For Closure

Phase 15 is complete when:

- the local verification matrix above remains green;
- the optional `sklearn` mypy boundary is committed and GitHub Actions passes;
- `plan/README.md` points to this closure audit;
- Phase 16/17 items are tracked in their own handoff files;
- no runtime ML, real-money execution, remote deployment, or cross-bank routing
  behavior is introduced.
