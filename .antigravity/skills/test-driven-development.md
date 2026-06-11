# Test-Driven Development Skill (test-driven-development)

## 1. Purpose
Establishes Test-Driven Development (TDD) discipline for AI agents and developers working on SilverPilot. Focuses on the "Red-Green-Refactor" cycle to prevent production regressions, design cleaner decoupled modular scopes, and ensure tests are written *before* or *simultaneously with* feature implementation.

---

## 2. The TDD Workflow (Red-Green-Refactor)

1.  **RED Phase (Write the Test First):**
    *   Before adding any new API endpoint, database query, or risk filter, write a failing unit or integration test case inside the relevant test file (`tests/test_*.py`).
    *   The test must assert exact behaviors, return schemas, or exception conditions.
    *   Execute the test suite and confirm that it fails (returns exit code > 0 or raises `AssertionError`). This proves the test is actively checking the missing capability.
2.  **GREEN Phase (Write Minimal Code to Pass):**
    *   Write the simplest, most direct production code required to satisfy the failing test case.
    *   Do not over-engineer or add out-of-scope refactoring in this step.
    *   Execute the test case again and verify that it passes (turns green).
3.  **REFACTOR Phase (Clean the Implementation):**
    *   Refactor the written production code to eliminate duplicates, align with SOLID/DRY principles, enforce type safety, and clean imports.
    *   Refactor the test code to ensure AAA clarity, parameterized cases, and accurate mocks.
    *   Re-run the test suite to verify that the refactoring introduced **zero** functional regressions.

---

## 3. TDD Validation Rules

*   **No Code Without Test:** Never propose backend services or logical adjustments without adding a corresponding test case verifying the change.
*   **Test Boundary Conditions:** TDD test cases must cover boundary and extreme cases:
    *   Null values (`None` properties).
    *   Empty data lists or collections.
    *   Out-of-bound ranges (e.g. negative balances, zero transaction sizes).
    *   Network timeouts and external API exceptions.
*   **Prevent False Positives:** Verify that test assertions are precise enough to fail when logical bugs are deliberately injected into the production module.
