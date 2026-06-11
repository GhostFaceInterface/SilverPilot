# General Coding Skills

## 1. Purpose
Defines the core software engineering and architectural standards for Python code in the SilverPilot project. Enforces clean, type-safe, maintainable, and secure development practices.

## 2. Rules
- **Type Safety:** All Python code must use explicit type hints on function parameters, return values, and variable definitions.
- **SOLID & DRY:** Code must be modular, adhering to Single Responsibility. Avoid duplicating code, but do not create unnecessary levels of abstraction (simple DRY).
- **Hata Yönetimi (Error Handling):** Never catch generic `Exception` without re-raising or logging. Use specific, domain-defined exceptions.
- **Logging:** Log events using appropriate levels (`debug` for flow, `info` for major lifecycle, `warning` for degradations, `error` for exceptions). Never log sensitive data.
- **Dependency Control:** Do not introduce third-party libraries without explicit review and approval. Leverage existing standard library tools first.
- **Secret Security:** Never hardcode API keys, passwords, database URLs, or configurations. Load them dynamically from environment variables.

## 3. Recommended Patterns
- Keep functions short (<50 lines) and highly focused.
- Async-by-default for I/O operations (network, database calls).
- Wrap external integrations with try-except blocks and explicit logging.
- Use Python's dataclasses or simple classes to pass structured internal data.

## 4. Anti-Patterns
- **Generic Catch-All:** `try: ... except: pass` or `except Exception:` without logging the traceback.
- **Hardcoded Credentials:** Storing `.env` properties, credentials, or development constants directly in codebase.
- **Deep Nesting:** Multiple nested loops or condition layers (prefer early returns).
- **Abuse of Abstractions:** Creating elaborate interface patterns for simple Python modules.

## 5. Checklist
- [ ] Are type hints defined for all function parameters and return values?
- [ ] Are all functions under 50 lines?
- [ ] Are credentials, secret keys, or URLs hardcoded? (Must be false)
- [ ] Are specific exception classes used instead of generic exceptions?
- [ ] Have you confirmed no new third-party packages were added to requirements?

## 6. Example Guidance
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DataRetrievalError(Exception):
    """Custom exception for data extraction failures."""
    pass

async def fetch_macro_rate(series_id: str) -> Optional[float]:
    """Fetches a macro-economic data point from configured environmental values."""
    if not series_id:
        logger.warning("Empty series ID passed to fetch_macro_rate.")
        return None
        
    try:
        # Example async network operation logic
        rate = 4.25  
        logger.debug("Successfully retrieved series %s: %s", series_id, rate)
        return rate
    except Exception as exc:
        logger.error("Failed to retrieve series %s due to: %s", series_id, str(exc), exc_info=True)
        raise DataRetrievalError("Network extraction failure") from exc
```
