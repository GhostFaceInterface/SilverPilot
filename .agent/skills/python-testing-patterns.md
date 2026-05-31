# Python Testing Patterns (pytest best-practices)

## 1. Purpose
Provides senior-level design patterns and constraints for implementing unit and integration tests in SilverPilot using `pytest`. Ensures that all async workflows, database sessions, and mathematical indicators are tested under isolated, deterministic conditions.

---

## 2. Core Python Testing Rules

### A. Fixture Lifecycle & Scopes
*   **Database Isolation:** Database sessions in tests must always use nested transactions (`db.begin_nested()`) and rollbacks inside a `yield` fixture to ensure that test mutations are never persisted.
    ```python
    @pytest.fixture
    def db_session():
        # Setup static static engine & SessionLocal
        connection = engine.connect()
        transaction = connection.begin()
        session = SessionLocal(bind=connection)
        
        # Nested transaction for individual test isolation
        nested = connection.begin_nested()
        
        yield session
        
        session.close()
        transaction.rollback()
        connection.close()
    ```
*   **Avoid Global State Mutation:** Fixtures that modify `Settings` or environment variables must yield, and restore the original settings in a `finally` block or teardown phase.

### B. Asynchronous Testing (`pytest.mark.anyio` / `pytest-asyncio`)
*   **Explicit Loop Integration:** When testing `async def` functions, always annotate the test case with `@pytest.mark.anyio`.
*   **Awaiting Coroutines:** Never forget to `await` async function executions inside test blocks.
*   **AsyncMock for Telemetry:** When mocking async services (e.g. LLM calls or Telegram dispatchers), use `unittest.mock.AsyncMock` instead of standard `MagicMock` to allow accurate awaiting.

### C. Test Case Parameterization (`@pytest.mark.parametrize`)
*   **Avoid Loop Duplication:** If testing a calculation or filter against multiple inputs (e.g., testing `calculate_rsi` with diverse price vectors), utilize pytest parametrization instead of using raw `for` loops inside a single test case. This keeps test failures highly isolated and scannable.
    ```python
    @pytest.mark.parametrize("price_list, expected_rsi", [
        ([10, 11, 12, 11, 10], 50.0),
        ([20, 20, 20, 20, 20], 0.0),
    ])
    def test_rsi_calculations(price_list, expected_rsi):
        ...
    ```

### D. AAA Pattern Assertion Formatting
*   **Act and Assert Separation:** Keep assert blocks focused. Do not mix function calls inside assert lines. Store results in descriptive variables, then perform equality or delta bounds checks.
*   **Delta Tolerance:** When asserting float or Decimal financial amounts (e.g. cash balances or portfolio values), always use `pytest.approx` or delta thresholds (`abs(val1 - val2) < 1e-5`) to avoid minor floating-point precision mismatches breaking builds.
