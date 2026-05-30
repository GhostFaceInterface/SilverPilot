---
type: feedback
created: 2026-05-18
updated: 2026-05-30
---


# Feedback History

## Design Rules
- **No Cliché Purple:** Purple, indigo, and violet gradients are banned by default as they represent AI-design clichés.
- **No Library Assumptions:** Never inject UI component libraries (such as shadcn/ui, Radix, Chakra) without asking first. Proactively ask before coding.
- **Premium Aesthetics:** Avoid rounded-everything defaults. Sharp edges, high contrast, and strategic micro-animations are favored.

## Test Engineering & Bug Prevention
- **Avoid Implicit Imports in Mocks:** When building mock tests that mimic network transports or delays (e.g. `mock_transport` side-effects utilizing `time.sleep`), ensure that all basic libraries (like `time`) are explicitly imported at the top of the test file (`test_collectors.py`). Never assume they are globally available or transitively imported.
- **Synchronize Mock Data and Validation Thresholds:** When simulating error states (like inverted buy/sell spreads or extreme percentage ranges) in tests, calculate and assert exact thresholds aligned with production check formulas. E.g., if buy=37.0 and sell=35.0, this is an inverted spread (Anomaly 1) and must be blocked directly. Keep test mocks robustly mapped to these formulas.
- **Clean Telemetry on Balance Reset:** When resetting a paper portfolio's cash balance to a starting balance (e.g. $2500 USD), you must completely purge all historical `paper_trades` and `portfolio_snapshots` for that portfolio ID from the database. Failure to do so causes the risk engine's lookback realized loss calculation (`_realized_loss_since`) to query old transactions, leading to a persistent `WEEKLY_LOSS_LIMIT_REACHED` hard block veto that blocks all incoming trades.

## DevOps & CI/CD Bug Prevention
- **Avoid Giant Inline SSH Command Strings in CI Configs:** Long inline SSH command chains in `.github/workflows/ci.yml` joined by `&&` are extremely fragile and difficult to debug. Additionally, they run inside a non-interactive shell (often `/bin/sh` or `dash` on Ubuntu VPS) which lacks bash-specific features (e.g. `{1..10}` loop brace expansions). Always write a dedicated bash script starting with `#!/usr/bin/env bash` (such as `scripts/vps_smoke.sh`) and execute it directly from the CI configuration.
- **Implement Soft Failures for Off-Market Stale Data:** Financial data providers (such as Yahoo Finance SI=F futures query) can fail with `STALE_DATA` during weekends, holidays (e.g., Memorial Day), or off-market hours. Ensure that data collectors run with soft-failure handling (`|| echo` or `|| log_warning`) in deployment and smoke test scripts so that expected data gaps do not halt or crash the CI/CD pipeline.


