# SilverPilot Phase Plan Handoff

`ROADMAP.md` remains the canonical product and phase source. This directory is
an implementation handoff companion: it records the current audit state for the
completed Phase 0-14 slice, the deployment-readiness gate before Phase 14, and
the offline ML experiment boundary.

The current implementation has completed Phase 14: Offline ML edge experiments
locally. Phase 15 records the roadmap-code closure audit and separates verified
Phase 0-14 behavior from Phase 16/17 hardening. Runtime ML remains explicitly
out of scope until a future promotion gate.

## Phase Status

| Phase | Status | Plan file |
| --- | --- | --- |
| Phase 0: Repository reset and project skeleton | PASS | `phase-00-audit-repository-skeleton.md` |
| Phase 1: Domain model and database schema | PASS | `phase-01-audit-domain-db.md` |
| Phase 2A: Kuveyt Turk source feasibility spike | PASS | `phase-02a-audit-kuveyt-feasibility.md` |
| Phase 2B: Kuveyt Turk provider implementation | PASS (naming hygiene resolved) | `phase-02b-audit-kuveyt-provider.md` |
| Phase 3: Price storage and bar builder | PASS | `phase-03-audit-price-storage-bars.md` |
| Phase 4: Indicator service | PASS | `phase-04-audit-indicators.md` |
| Phase 5: Rule-based regime detector | PASS | `phase-05-regime-detector.md` |
| Phase 6: One simple strategy | PASS | `phase-06-simple-strategy.md` |
| Phase 7: Risk manager | PASS | `phase-07-risk-manager.md` |
| Phase 8: Paper broker and ledger | PASS | `phase-08-paper-broker-ledger.md` |
| Phase 9: Backtest engine | PASS | `phase-09-backtest-engine.md` |
| Phase 10: REST API | PASS | `phase-10-rest-api.md` |
| Phase 11: Telegram adapter | PASS | `phase-11-telegram-adapter.md` |
| Phase 12: News/Hermes risk module | PASS | `phase-12-news-hermes-risk.md` |
| Phase 13: Reporting dashboard data | PASS | `phase-13-reporting-dashboard-data.md` |
| Deployment readiness before Phase 14 | PASS | `deployment-readiness-before-phase-14.md` |
| Phase 14: Offline ML edge experiments | PASS | `phase-14-ml-experiments.md` |
| Phase 15: Roadmap-code closure audit | PASS | `phase-15-architecture-closure.md` |

Phase 14 is complete as an offline experiment lane only. ML has no runtime
authority over strategy, risk, broker, API, Telegram, scheduler, collector, or
order behavior. Remote CI must pass after the optional-ML mypy fix is pushed
before making an unqualified Phase 0-14 completion claim; GitHub Actions passed
for commit `43d3b2d`.

## Verification Matrix

The Phase 0-14 audit and deployment-readiness gate are based on local source
evidence and the latest verification run:

| Check | Observed result |
| --- | --- |
| `pytest` | 143 passed |
| `ruff check .` | passed |
| `ruff format --check .` | passed |
| `mypy` | passed |
| `bash .codex/scripts/verify-docker.sh` | passed |
| `bash .codex/scripts/verify-docker.sh --build` | UNKNOWN/SKIPPED: Docker daemon not running |
| latest GitHub Actions CI on `main` | passed for commit `43d3b2d` |

Rerun the same commands after each phase to prove code and documentation remain
aligned.

Phase 7 hardening before Phase 8 added account-bound execution validation,
bank precision/minimum sizing, explicit expected-edge context, and
hash-based indicator snapshot lookup for Phase 5/6 consumers. Re-run the
verification matrix after this hardening before starting Phase 8.

Phase 8 added `PaperBroker`, `LedgerService`, paper orders, paper trades,
positions, and immutable ledger entries. Buy execution uses bank sell price;
sell execution uses bank buy price; same-quote round trips lose money after
spread and configured costs.

Phase 9 added deterministic dataset snapshots, `BacktestEngine`, simulated
clock replay, persisted backtest reports, cost-inclusive PnL, rejected/no-trade
reporting, portfolio curves, and shared strategy/risk/broker/ledger execution
against isolated simulated accounts.

Phase 10 added read-only `/api/v1` REST endpoints through
`src/silverpilot/app/api`, with Pydantic response schemas, pagination metadata,
structured not-found responses, and an `ApiQueryService` that keeps database
queries out of route handlers.

Phase 11 added optional Telegram command formatting and notification delivery
through `src/silverpilot/app/notifications`. Telegram is disabled by default,
uses injected transport for sends, and consumes API DTOs instead of owning
trading, risk, broker, backtest, or ledger decisions.

Phase 12 added `src/silverpilot/app/news`, news source/event/event-risk schema,
Hermes risk JSON generation, idempotent news/event-risk persistence, and
RiskManager-only event-risk veto/no-trade/reduction handling. Stale news is
ignored and event-risk context cannot create strategy signals, orders, trades,
positions, or ledger entries.

Phase 13 added read-only account dashboard reporting through
`GET /api/v1/reports/accounts/{account_id}/dashboard`. The response combines
portfolio valuation, PnL, risk summary, and account health in one JSON contract
for future web/mobile clients. Valuations use fresh indicative bank buy quotes
and surface stale/missing quote status instead of fabricating prices.

Deployment readiness before Phase 14 added backend container packaging,
Docker Compose services for Postgres, one-shot migrations, API, and an optional
bounded collector profile. It also added a VPS deployment runbook with local
gates, migration gates, health checks, rollback requirements, and explicit
approval rules. Remote VPS deployment status is tracked outside this phase
handoff; do not infer a new deployment from Phase 14.

Phase 14 added `src/silverpilot/app/ml_experiments`, the
`silverpilot-ml-experiment` CLI, optional `ml` dependency extra, ML metadata
tables, deterministic `mlruns/phase14/` dataset artifacts, chronological
embargo validation, rule-only/dummy/logistic experiment reports, and
`insufficient_data` handling. It extracts a pure `trend_up_pullback` evaluator
so offline candidate generation matches strategy behavior without persisting
strategy runs or trade intents.

Phase 15 added a closure audit that classifies roadmap-only concepts after
Phase 14. `ExecutionPremiumService`, `ExecutionPremiumSnapshot`, concrete
database-backed unit conversion, detailed cost breakdowns, and `QuoteUnit` /
`ExecutionUnit` / `InstrumentUnit` terminology are deferred to Phase 16.
Offline ML productization gates and runtime-boundary regressions are deferred
to Phase 17.

## Scope Rules

- Implement only SilverPilot's backend-first paper-trading simulation core.
- Treat Kuveyt Turk public quotes as indicative bank quotes, not guaranteed
  executable prices.
- Do not add runtime ML, dashboard UI, multi-bank routing, real money execution,
  Telegram-owned decisions, live news fetching, report persistence, or mutating
  remote API behavior inside the Phase 14 offline experiment boundary.
- Do not run remote deployment, SSH service changes, production smoke checks,
  or secret inspection without explicit user approval.
- Keep runtime financial/data code under `src/silverpilot/app/...`; do not
  invent a root `/agents` application directory.
