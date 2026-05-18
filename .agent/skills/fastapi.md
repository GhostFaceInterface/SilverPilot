# FastAPI Coding Skills

## 1. Purpose
Defines standard patterns for writing APIs, request/response payload validations using Pydantic, dependency injection routing, and modular controller structures in SilverPilot.

## 2. Rules
- **Service Layer Separation:** FastAPI Router handlers (endpoints) must act only as traffic controllers. All business logic, DB mutations, and risk checks must reside in Service modules.
- **Explicit Schemas:** Every endpoint must use explicit Pydantic v2 schemas for both input validation (`body`, `query`) and output serialization (`response_model`).
- **Dependency Injection (DI):** Use FastAPI's `Depends()` pattern to inject database sessions (`AsyncSession`), utility config dependencies, and authentication modules.
- **HTTP Status Codes:** Adhere to REST specifications. Use `201 Created` for creations, `204 No Content` for updates/deletions yielding no output, and appropriate `4xx` statuses for validations/failures.
- **Pattern Check:** Before adding a route, inspect the active directory (`routers/`) to ensure consistent naming conventions and URL path styles.

## 3. Recommended Patterns
- Return clean structured objects instead of raw dictionaries.
- Use explicit validation logic inside Pydantic schemas using `@field_validator`.
- Centralize custom error mapping into FastAPI exception handlers (`HTTPException` with explicit detail payloads).

## 4. Anti-Patterns
- **Fat Routers:** Performing raw DB queries or heavy math checks directly inside the endpoint handler function.
- **Raw Dict Output:** Returning un-validated Python `dict` objects instead of using `response_model`.
- **Global DB Sessions:** Creating database connections inside routers bypassing the dependency injection framework.

## 5. Checklist
- [ ] Is business logic separated into a dedicated Service module?
- [ ] Are Pydantic schemas defined for both input request and output response?
- [ ] Is the database session (`AsyncSession`) injected via `Depends()`?
- [ ] Are appropriate HTTP status codes set (e.g. 201 for POST creations)?
- [ ] Did you check `routers/` to ensure naming consistency?

## 6. Example Guidance
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.services.trade import PaperTradeService

router = APIRouter(prefix="/paper-trades", tags=["Trading"])

class TradeCreateSchema(BaseModel):
    symbol: str = Field(..., max_length=10, description="Trading asset symbol")
    quantity: float = Field(..., gt=0)

class TradeResponseSchema(BaseModel):
    trade_id: int
    symbol: str
    status: str

@router.post("", response_model=TradeResponseSchema, status_code=status.HTTP_201_CREATED)
async def execute_paper_trade(
    payload: TradeCreateSchema,
    db: AsyncSession = Depends(get_db_session)
) -> TradeResponseSchema:
    """FastAPI endpoint executing simulated paper trades."""
    service = PaperTradeService(db)
    result = await service.create_trade(symbol=payload.symbol, quantity=payload.quantity)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Trade blocked by risk policies"
        )
        
    return TradeResponseSchema(
        trade_id=result.id,
        symbol=result.symbol,
        status=result.status
    )
```
