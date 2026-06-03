# Paper Trading & Risk Policy Skill

Use this manual when editing trading strategy rules, portfolio calculations, or risk engine checks.

## 🛡️ Risk Rules & Limits

- **Strictly Virtual:** The system operates using a virtual starting balance ($600 USD original base). No real bank account API integration is permitted.
- **Weekly Loss Limit:** Reaching the weekly loss limit triggers a persistent `WEEKLY_LOSS_LIMIT_REACHED` hard block veto that blocks all incoming trades.
- **Clean Telemetry on Reset:** When resetting cash balance, you must purge all historical records from `paper_trades` and `portfolio_snapshots` to prevent old transactions from triggering weekly loss calculations.

---

## 🕒 COMEX Off-Hours Bypass Rule

- **Weekend/Maintenance Stale Data:** Since scrapers do not fetch new prices when COMEX is closed (Friday 17:00 ET to Sunday 18:00 ET, and daily 17:00-18:00 ET), the system naturally raises a `STALE_DATA` error.
- **Off-Hours Bypass:** The risk engine automatically bypasses the stale-price veto during these specific closed windows to allow weekend simulation on the last known closing price.
- **Test Sandbox Safety:** To guarantee test determinism, the bypass evaluations always return `False` when `settings.app_env == "test"`.
