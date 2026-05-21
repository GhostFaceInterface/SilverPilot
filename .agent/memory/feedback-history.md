---
type: feedback
created: 2026-05-18
updated: 2026-05-21
---

# Feedback History

## Design Rules
- **No Cliché Purple:** Purple, indigo, and violet gradients are banned by default as they represent AI-design clichés.
- **No Library Assumptions:** Never inject UI component libraries (such as shadcn/ui, Radix, Chakra) without asking first. Proactively ask before coding.
- **Premium Aesthetics:** Avoid rounded-everything defaults. Sharp edges, high contrast, and strategic micro-animations are favored.

## Test Engineering & Bug Prevention
- **Avoid Implicit Imports in Mocks:** When building mock tests that mimic network transports or delays (e.g. `mock_transport` side-effects utilizing `time.sleep`), ensure that all basic libraries (like `time`) are explicitly imported at the top of the test file (`test_collectors.py`). Never assume they are globally available or transitively imported.
- **Synchronize Mock Data and Validation Thresholds:** When simulating error states (like inverted buy/sell spreads or extreme percentage ranges) in tests, calculate and assert exact thresholds aligned with production check formulas. E.g., if buy=37.0 and sell=35.0, this is an inverted spread (Anomaly 1) and must be blocked directly. Keep test mocks robustly mapped to these formulas.
