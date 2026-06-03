# Financial Agent Runtime Skill

Use this manual when auditing or interacting with the runtime financial and data agents residing under `/agents`.

## 🤖 Runtime Agent Core Boundaries

- **FastAPI HTTP Boundary:** Runtime agents executing on the VPS must **never** connect directly to the PostgreSQL database ports. They must interact with the system database exclusively via FastAPI HTTP endpoints (e.g., `/risk/status`, `/agent/memory`).
- **Memory Routing:** Agents must read and write state through the designated memory REST API endpoints to capture state context without leaking PostgreSQL connection slots.

---

## 💸 Budget Guard Thresholds

- **Limit Security:** To prevent token leaks or billing runaways, the system executes pre-flight checks against a budget safety limiter (`apps/api/app/llm/budget_guard.py`).
- **Budget Bound:** The default daily token cost limit is set to **$3.00 USD** (via `DEEPSEEK_DAILY_BUDGET_USD`). Exceeding this triggers a `BudgetExceededError`, blocking further agent calls.

---

## 📈 Veto & Blended Consensus Logic

- **Hermes Sentiment Veto:** A weighted sentiment score is calculated across multiple authority sources (e.g., Kitco, Reuters, Investing.com).
- If the sentiment score falls below `HERMES_VETO_THRESHOLD` (default `-0.45`), `BUY` signals are overridden to `HOLD` with the warning label `AGENT_VETO_HERMES_BEARISH_NEWS`.
- **Supreme Arbiter (Yüce Hakem):** Conflicting advisor sentiments are escalated to a `deepseek-v4-pro` model instance to determine a final, unified, and risk-safe verdict.
