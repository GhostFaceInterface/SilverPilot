# FastAPI & SQLAlchemy Development Skill

Use this manual when designing API endpoints, querying database tables, or modifying models.

## 🛠️ Code Conventions

### 1. Model Isolation & Directory Structure
- Models live in `apps/api/app/models/`.
- Schemas (Pydantic models) live in `apps/api/app/schemas/`.
- Database interaction queries must live in `apps/api/app/services/` or dedicated model classmethods. Do **not** write raw queries directly inside router endpoints.

### 2. Async Session Management
- All database operations in FastAPI routes must use the standard dependency injection pattern:
  ```python
  from apps.api.app.database import get_db
  from sqlalchemy.ext.asyncio import AsyncSession
  
  @router.get("/data")
  async def read_data(db: AsyncSession = Depends(get_db)):
      ...
  ```
- Lifespan tasks or background consumer loops running outside FastAPI requests should use `SessionLocal` with context managers to guarantee immediate cleanup:
  ```python
  with SessionLocal() as db:
      # do operations
  ```

---

## 🚫 N+1 Query Prevention

- Never query relationships inside loops. 
- Use SQLAlchemy's `selectinload` or `joinedload` options to eagerly load related tables:
  ```python
  from sqlalchemy.orm import selectinload
  from sqlalchemy.future import select

  stmt = select(PriceSnapshot).options(selectinload(PriceSnapshot.details))
  result = await db.execute(stmt)
  ```
- Utilize O(1) query patterns. For historical backfills, fetch existing timestamps into memory sets before looping, rather than querying the database for every row.

---

## 🔒 Transaction Safety

- Every database mutation execution loop must run inside a transaction block.
- Always implement transaction rollback on script errors:
  ```python
  try:
      # batch insert logic
      await db.commit()
  except Exception as e:
      await db.rollback()
      raise e
  ```
