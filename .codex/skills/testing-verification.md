# Testing & Verification Safety Skill

Use this manual when writing unit, integration, or E2E tests, verifying mock boundaries, or analyzing test failures.

## 🧪 Testing Environment & DB Isolation

- **In-Memory SQLite:** Standard unit/integration tests must execute using SQLite in-memory databases (`sqlite+pysqlite:///:memory:`) to guarantee isolation.
- ** purges on reset:** Purge `paper_trades` and `portfolio_snapshots` tables when executing starting balance resets to prevent weekly loss calculation errors.

---

## 🚫 Network Sandboxing & Mock Drift

- **Mock Import Rules:** Ensure all mock side-effects have explicit library imports at the top of the test file (e.g., `import time` for delays).
- **On-Demand Scrapers Mocking:** Always mock on-demand news/price collectors inside route tests. Running tests on empty database scopes will trigger live scrapers, resulting in network leakage and test errors (e.g. 401 unauthorized).
- **Namespace Drift Patching:** Target the mock patch exactly at the module where the object is imported and instantiated (the ultimate importer namespace), NOT the importing parent.
  - *Correct:* `mock.patch("app.services.telegram.Bot")`
  - *Incorrect:* `mock.patch("app.services.auto_trader.Bot")` (causes live API leakage).

---

## 🚦 Execution Quality Gates

- **Ruff Lint Enforcement:** Pre-commit hooks run Ruff validation on Python files. Fix unused variables and mark deferred imports with `# noqa: E402`.
- **AAA Pattern:** Organize tests under Arrange, Act, Assert.
- **Pass Gate:** No commits can be staged or pushed unless `pytest` execution returns **100% green** (zero failures or warning drifts).
