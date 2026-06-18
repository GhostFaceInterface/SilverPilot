# SilverPilot Phase Plan Handoff

`ROADMAP.md` remains the canonical product and phase source. This directory is
an implementation handoff companion: it records the current audit state for the
completed Phase 0-7 slice and the detailed execution plan through Phase 9.

The current implementation is entering Phase 8: Paper broker and ledger.

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
| Phase 8: Paper broker and ledger | NEXT | `phase-08-paper-broker-ledger.md` |
| Phase 9: Backtest engine | Planned | `phase-09-backtest-engine.md` |

Phase 10 REST API is the next boundary after Phase 9 and is intentionally out
of scope for this handoff.

## Verification Matrix

The Phase 0-7 audit is based on local source evidence and the latest
verification run:

| Check | Observed result |
| --- | --- |
| `pytest` | 87 passed |
| `ruff check .` | passed |
| `ruff format --check .` | passed |
| `mypy` | passed |

Rerun the same commands after each phase to prove code and documentation remain
aligned.

Phase 7 hardening before Phase 8 added account-bound execution validation,
bank precision/minimum sizing, explicit expected-edge context, and
hash-based indicator snapshot lookup for Phase 5/6 consumers. Re-run the
verification matrix after this hardening before starting Phase 8.

## Scope Rules

- Implement only SilverPilot's backend-first paper-trading simulation core.
- Treat Kuveyt Turk public quotes as indicative bank quotes, not guaranteed
  executable prices.
- Do not add Hermes, ML, Telegram, dashboard, Docker, multi-bank routing, real
  money execution, or Phase 10 API work inside Phase 5-9.
- Keep runtime financial/data code under `src/silverpilot/app/...`; do not
  invent a root `/agents` application directory.
