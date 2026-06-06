# SilverPilot Phased Implementation Plan

> [!IMPORTANT]
> This is the single canonical execution artifact for implementation sessions.
> `docs/ROADMAP.md` is not used for current phase routing.

## Purpose

This document is the working artifact for the phase-by-phase hardening plan.
Each phase is implemented, validated, and deployed independently before the
next phase begins.

## Current Status

- Current official phase: Phase 3-5 integration verification pending VPS smoke.

- Phase 1: Indicator readiness gate and consumption sync. Completed.
- Phase 2: Indicator engine v2 and additive technical fields. Completed.
- Phase 3: Multi-timeframe bar and indicator synchronization. Implemented locally.
  Runtime now enforces `1d -> 1h -> 5m` usage and fails closed on missing/stale
  or misaligned inputs. VPS smoke remains the closeout gate.
- Phase 4: Deterministic Strategy V2. Implemented locally and under regression test.
  VPS smoke remains the true-start verification gate.
- Phase 5: Trade intent bridge between strategy and paper execution. Implemented locally.
  VPS smoke remains the activation gate.
- Agent/ML/DeepSeek/OpenClaw expansion track: frozen backlog until Phase 5 is complete.

## Phase Rules

1. Keep each phase narrowly scoped.
2. Validate locally before commit.
3. Deploy only after the phase tests pass.
4. Do not start the next phase until the current phase is smoke-tested.
5. Keep additive schema changes nullable unless the phase explicitly requires a break.

## Next Phase Objective

Complete VPS smoke validation for the integrated Phase 3-5 hardening slice and
only then resume any broader agent/ML expansion. The enforced timeframe roles
remain:

- `1d`: trend and regime filter
- `1h`: entry decision
- `5m`: execution freshness only

Execution must fail closed when the daily trend is missing, the hourly layer is
stale, or timeframe/source alignment is broken.
