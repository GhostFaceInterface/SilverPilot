# Recurring Failures Checklist

Use this checklist during diagnosis or pre-push review to avoid repeating historic engineering mistakes in SilverPilot.

## ⚠️ Database & Telemetry Failures

- **Balance Reset Telemetry:**
  - *Symptom:* Persistent `WEEKLY_LOSS_LIMIT_REACHED` block even after resetting portfolio cash balance.
  - *Root Cause:* Failing to delete existing records from `paper_trades` and `portfolio_snapshots` for the modified portfolio ID, causing the weekly loss check to compute metrics on stale transactions.
  - *Fix:* Always purge trade and snapshot histories when resetting cash balance.

- **Double-Conversion Traps:**
  - *Symptom:* Trades executing at 1/45th of the actual price value.
  - *Root Cause:* Asset currency mismatch (e.g., storing USD pricing data but setting `Asset.currency = "TRY"`, which triggers an unintended conversion division by USD/TRY rate).
  - *Fix:* Ensure stored snapshot currency match model properties. Use separate test assets (like `XAG_TRY`) instead of overloading production symbols.

---

## 🐍 Async & Mocking Pitfalls

- **Un-awaited Coroutines in Synchronous Contexts:**
  - *Symptom:* Background dispatches (e.g., Telegram alerts) silently failing/cancelling.
  - *Root Cause:* Running async functions via `asyncio.run()` but scheduling subsequent tasks via `asyncio.ensure_future` without awaiting them before the loop shuts down.
  - *Fix:* Always directly `await` all notification dispatches.

- **Target Namespace Drift in Patches:**
  - *Symptom:* Mock assertions fail, and tests leak live network connections.
  - *Root Cause:* Patching the wrong module namespace (e.g., patching `app.services.auto_trader.Bot` instead of the importing service file `app.services.telegram.Bot`).
  - *Fix:* Always patch the target namespace where the dependency is loaded and used.

- **Implicit Imports in Mocks:**
  - *Symptom:* Test crashes complaining about undefined libraries.
  - *Root Cause:* Mock code using side-effects like `time.sleep` without importing `time` inside the specific test file.
  - *Fix:* Explicitly import all basic libraries at the top of test files.
