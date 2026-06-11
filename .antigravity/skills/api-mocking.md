# API Mocking & Observability Skill (api-mocking)

## 1. Purpose
Establishes standardized procedures for mocking third-party REST/gRPC/Bot APIs (like Telegram, Yahoo Finance, metals-dev, and DeepSeek LLM) inside SilverPilot test suites. Ensures mock target accuracy, prevents external network leaks, and verifies execution paths deterministically.

---

## 2. API Mocking Rules & Standards

### A. The Import Target Rule (Targeting Namespace)
*   **Crucial Rule:** Always target `unittest.mock.patch` at the namespace where the object is **imported and instantiated** in the production code under test, never at the origin module.
    *   *Example:* If `auto_trader.py` imports `send_telegram_message` from `app.services.telegram` and executes it, patch the target inside the trader namespace or the central dispatcher namespace depending on where the instantiation happens:
        *   `patch("app.services.telegram.Bot")` (because Bot is instantiated inside the telegram service module).

### B. Mocking HTTP Clients (`httpx` / `requests`)
*   **httpx.AsyncClient Patching:** When mocking asynchronous network transactions (e.g. LLM Gateway queries), mock the client post or get method and return an `AsyncMock` response containing `.json()` lambdas.
    ```python
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"result": "success"}
        mock_post.return_value = mock_response
    ```

### C. Error State Simulation
*   **Fail Gracefully:** Mocks must not only test happy paths. Always write corresponding test cases that force the mock to raise standard client exceptions:
    *   `Bot.send_message` raising `telegram.error.RetryAfter` or `telegram.error.TelegramError`.
    *   Verify that parent modules gracefully handle these exceptions, log warning tracebacks, and commit transactional database sessions safely without crashing.

### D. Mock Call Assertions
*   **Verify parameters:** Never use generic `assert mock.called` when verifying crucial transactions. Always use precise, targeted assertions checking exactly what arguments were dispatched:
    ```python
    mock_send.assert_called_once_with(
        chat_id="123456",
        text="Expected payload...",
        parse_mode="HTML"
    )
    ```

### E. Asserting Await Behavior
*   For asynchronous mocks (`AsyncMock`), ensure the test explicitly asserts that the mock was **awaited** (e.g., `mock_send.assert_awaited_once()`) to prevent un-awaited background tasks from silently completing or getting cancelled.
