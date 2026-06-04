---
name: "financial-risk-regression"
description: "Codex-local skill bundle for paper-trading, PnL, risk policy, collector pricing, and ML veto regressions."
---

# Financial Risk Regression

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Preserve no-real-money and paper-trading boundaries.
- Validate financial formulas with deterministic fixtures.
- Use `Decimal` where runtime code uses money or quantities.
- Test negative, zero, stale, missing-data, and closed-market cases.
- Risk guardrails must not be bypassed silently.

## Critical Checks
- Unrealized PnL uses live sell price and average buy cost.
- Net PnL includes realized plus live unrealized value, or portfolio value minus initial cash.
- Collector health ignores inactive obsolete sources.
- ML model availability does not silently disable safety.
- Weekly loss and stale-data guardrails remain deterministic in tests.

## Evidence
- Formula or guardrail tested.
- Input fixture and expected result.
- Regression test name.
- Untested financial/risk uncertainty.
