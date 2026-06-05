# SilverPilot Phased Implementation Plan

## Purpose

This document is the working artifact for the phase-by-phase hardening plan.
Each phase is implemented, validated, and deployed independently before the
next phase begins.

## Current Status

- Phase 1: Indicator readiness gate and consumption sync. Completed.
- Phase 2: Indicator engine v2 and additive technical fields. Completed.
- Phase 3: Multi-timeframe bar and indicator synchronization. In progress.
- Later phases: strategy confidence, trade intent, ML scorecard, backtest hardening,
  dashboard/Telegram control surface, 90-day shadow gate, manual micro-pilot.

## Phase Rules

1. Keep each phase narrowly scoped.
2. Validate locally before commit.
3. Deploy only after the phase tests pass.
4. Do not start the next phase until the current phase is smoke-tested.
5. Keep additive schema changes nullable unless the phase explicitly requires a break.

## Next Phase Objective

Phase 3 will align execution around synchronized `5m`, `1h`, and `1d` bar layers,
with strict timeframe isolation and no cross-timeframe reuse in indicator or regime
consumption.
