# SilverPilot Phase Plan

> [!IMPORTANT]
> This is the single canonical phase and status artifact for implementation
> routing.
>
> Official re-baseline label as of 2026-06-07: `Phase 5 re-baseline`.
>
> `README.md`, `PLAN.md`, `docs/ROADMAP.md`, and `docs/WORKLOG.md` are not
> phase authorities.

## Re-Baseline Matrix

| Phase | Status | Baseline |
| --- | --- | --- |
| Phase 1 | `complete` | Indicator readiness gate exists and is enforced in runtime consumption. |
| Phase 2 | `complete` | `technical-indicators-v2` persists the additive V2 indicator fields. |
| Phase 3 | `complete` | Runtime guardrails enforce `1d -> 1h -> 5m` roles and fail closed on missing, stale, or misaligned inputs. |
| Phase 4 | `partial` | Deterministic Strategy V2 exists, but it does not yet fully consume persisted V2 fields and the SELL guard set remains incomplete. |
| Phase 5 | `partial` | Signal-to-intent bridge exists in code, but there is no persisted `trade_intents` audit chain and the risk layer still lacks exposure/cooldown/cash-reserve/age/drawdown guards. |
| Phase 6 | `out-of-plan` | Dashboard, agent, and orchestration surfaces exist only as exploratory/non-canonical extensions. |
| Phase 7 | `out-of-plan` | ML inference audits and runtime agent expansion exist, but they are not allowed to redefine the deterministic core baseline. |
| Phase 8 | `out-of-plan` | Backtest, historical agent cache, and dataset work exist as exploratory/offline tooling, not canonical execution routing. |
| Phase 9 | `not started` | No canonical Phase 9 baseline is accepted yet. |
| Phase 10 | `not started` | No canonical Phase 10 baseline is accepted yet. |

## What Counts As Done Today

### Complete

- Indicator readiness gate and consumption sync are in place.
- `technical-indicators-v2` additive field persistence is in place.
- Runtime timeframe policy is enforced as `1d` trend, `1h` entry, `5m`
  execution freshness.
- A deterministic Strategy V2 skeleton exists.
- A signal-to-intent bridge exists between strategy output and paper execution.

### Partial

- Persisted V2 fields `adx_14`, `plus_di_14`, `minus_di_14`,
  `bb_bandwidth_20_2`, `bb_percent_b_20_2`, `atr_percent_14`,
  `rsi_slope_1`, and `macd_histogram_slope_1` are not yet fully consumed by
  decision logic.
- Strategy V2 SELL logic is still narrower than the intended deterministic
  guard set.
- Trade intents are runtime objects, not a persisted audit artifact linked to
  `signals`, `risk_decisions`, and `paper_trades`.
- Risk policy does not yet enforce max order percent, max position percent,
  min cash reserve, cooldown, min hold, max position age, or total drawdown
  blocks.

### Exploratory / Non-Canonical

- ML inference audits.
- Backtest scripts and dataset tooling.
- Dashboard agent surfaces and historical agent cache.
- Multi-agent orchestrator and related LLM fan-out paths.

## Freeze Policy

- Do not expand canonical agent or ML execution authority until Phase 4 and
  Phase 5 gaps are closed.
- Runtime remains paper-only and deterministic-core-first.
- Any ML behavior in the canonical path must remain advisory-only until the
  deterministic core and risk gaps below are complete.

## Locked Execution Order

1. Slice 1: Add a persisted `trade_intents` table and link it to `signals`,
   `risk_decisions`, and `paper_trades`; close the direct
   strategy-to-paper-trade shortcut.
2. Slice 2: Finish Strategy V2 with the already-persisted V2 indicator fields
   and make BUY/SELL rules deterministic and explainable.
3. Slice 3: Add risk guards for max order percent, max position percent, min
   cash reserve, cooldown, min hold, max position age, and total drawdown.
4. Slice 4: Keep ML advisory-only in the canonical flow, add 1d/3d/7d outcome
   tracking, and unify ML/backtest/dataset work around `XAG_GRAM` or an
   explicit `XAG -> XAG_GRAM` normalization contract.
5. Slice 5: Close mutating endpoint auth, Telegram webhook secret validation,
   kill switch, and raw prompt/response redaction-disable gaps.

## Validation Baseline

- Code is the primary truth source; markdown may only summarize verified code
  state.
- A previous targeted core audit reported `56 passed`; use that as historical
  context, not as a substitute for current verification.
- Add and keep a docs consistency check so `README.md`, `PLAN.md`, and
  `docs/ROADMAP.md` cannot silently drift away from this file again.
