# Test and Mock Integrity Skill (TIER 0 Quality Gate)

## 1. Purpose
This skill formalizes deterministic test verification, mock namespace alignment (preventing Mock Drift), network sandboxing, and test quality gates. Derived from the open-source community testing-qa frameworks, it ensures that all modifications in SilverPilot are accompanied by resilient, deterministic tests that reflect active codebase import paths.

---

## 2. Core Testing Principles (Tavizsiz Kalite Kuralları)

### A. The AAA Pattern (Arrange, Act, Assert)
All tests must strictly follow the AAA pattern to maintain readability and isolation:
*   **Arrange:** Set up database states, environment mock settings, and expected output values.
*   **Act:** Trigger the asynchronous function or service method being tested under clean database sessions.
*   **Assert:** Verify that outputs match mathematical expectations, exceptions are raised or handled gracefully, and mock boundaries are verified.

### B. Enforce Precise Target Namespaces in Patches (Mock Drift Prevention)
To prevent tests from silently executing real external connectors (e.g. attempting network dispatches to Telegram API or Yahoo Finance) and creating a false sense of security ("fake green tests"):
*   **Target the Ultimate Importer:** When using `unittest.mock.patch`, always target the namespace where the object is actually **imported and instantiated** in the runtime code, rather than obsolete imports in secondary files.
    *   *Incorrect:* `patch("app.services.auto_trader.Bot")` (if the Bot class is no longer imported or used there)
    *   *Correct:* `patch("app.services.telegram.Bot")` (where the Bot class is actually imported and executed)
*   **Clean Up Obsolete Imports:** During any refactor, scan files to remove dead imports (like `from telegram import Bot`) so that patching targets remain unambiguous.

### C. Complete Network and Socket Sandboxing
*   **No Live Connections:** Unit and integration tests must run in 100% network-isolated environments.
*   **Skepticism on Green Tests:** If a test completes successfully but mocks are not actively recording calls, verify immediately if a real HTTP client or socket transport was leaked during execution.

### D. Dead Test Purge
*   When a component is refactored, deprecating old execution paths, the corresponding legacy tests **MUST** be audited.
*   Either refactor legacy tests to match the new centralized interface, or delete obsolete test cases entirely to prevent "dead test code bloating" which yields false positives.

---

## 3. Step-by-Step Verification Protocol

When asked to audit code changes or test suites before Git push:

1.  **Git Diff Mapping:** Analyze the git status to find all modified/created Python modules.
2.  **Dependency & Import Audit:** For each changed production file, extract all active module-level imports. Identify which helper classes or network clients (e.g., `Bot`, `DeepSeekGateway`, `httpx.AsyncClient`) are executed.
3.  **Mock Target Audit:** Open corresponding test files (`tests/test_*.py`). Crosscheck every `patch(...)` string value against the actual import targets found in step 2. Ensure **zero** mock drift.
4.  **Coverage Assessment:** Verify that new branches, exception handling scopes, and dynamic indicators are covered by writing corresponding unit and integration test assertions.
5.  **Execution Check:** Run the specific test suites locally via `pytest` and assert 100% success.

---

## 4. Anti-Patterns to Ban

*   **Mock Drift Ignorance:** Accepting a successful test run when the patched namespace is obsolete, allowing real code to execute real socket dispatches.
*   **Uncontained Notification Side-Effects:** Letting notification helpers or non-transactional triggers throw exceptions that block/rollback the main transaction.
*   **Fixture Session Leaks:** Writing tests that mutate local files or persistent databases without executing proper rollbacks/cleanups in test fixtures.
