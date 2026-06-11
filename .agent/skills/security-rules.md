# Security Rules & OWASP 2025 Standards

## 1. Purpose
Defines the software security policy and compliance standards for the SilverPilot project. Enforces strict zero-trust validation, secret leak prevention, and safe coding practices to protect financial calculations and paper-trading metrics.

## 2. Rules
- **Zero-Trust Input Validation:** All API inputs, raw parameters, and incoming payloads must be strictly validated. Never trust client-side data without server-side verification.
- **SQL Injection Prevention:** Never construct SQL queries using string concatenation or raw formatting. Always use SQLAlchemy's parameterized query APIs or ORM-native expressions.
- **No Hardcoded Secrets:** Strictly no raw API keys, private tokens, passwords, or connection strings in code files. All configuration must be loaded via Environment Variables or verified vault providers.
- **Safe Subprocesses / Code Execution:** Never use `eval()`, `exec()`, or python's `subprocess` with `shell=True`. Validate all system commands against a strict whitelist.
- **Fail-Secure Principle:** If an exception occurs, the system must immediately deny the operation and revert changes. Never expose database structures, system file paths, or third-party API traces in user-facing error details.
- **IDOR Protection:** Authenticated actions must verify that the requesting user owns or has explicit permission for the target resource ID (e.g., portfolio, trades).

## 3. Recommended Patterns
- Use robust Pydantic v2 validation classes with strict numeric thresholds (e.g., `gt=0` for trade quantities).
- Centralize database session safety with async rollback handlers on session transaction failures.
- Store sensitive variables inside `.env` listed explicitly under `.gitignore`.
- Sanitize database queries containing external strings using SQLAlchemy parameters.

## 4. Anti-Patterns
- **Query Concatenation:** `session.execute(f"SELECT * FROM trades WHERE symbol = '{symbol}'")` -> **HIGH RISK**.
- **Exposing Internal Tracebacks:** Returning raw python `str(exc)` inside a FastAPI `HTTPException` detail.
- **Missing Auth Bindings:** Updating a portfolio balance without checking if the portfolio matches the token's user ID.
- **Weak Calculations:** Trusting calculations without verification gates (e.g., letting negative quantities pass validation).

## 5. Checklist
- [ ] Are all database operations parameterized or using safe SQLAlchemy expression styles?
- [ ] Are Pydantic schemas enforcing strict constraints (e.g. `gt=0`) for all transaction inputs?
- [ ] Is there absolutely zero hardcoded passwords, database URLs, or API keys in the code?
- [ ] Do API endpoints handling private records check resource ownership (IDOR protection)?
- [ ] Are custom exception details stripped of raw system information or stack traces?

## 6. Example Guidance
```python
# Safe parameterized query pattern
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.portfolio import Portfolio

async def get_portfolio_securely(session: AsyncSession, owner_id: int, portfolio_id: int) -> Portfolio | None:
    # Explicit ownership check prevents IDOR
    stmt = (
        select(Portfolio)
        .where(Portfolio.id == portfolio_id)
        .where(Portfolio.owner_id == owner_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```
