# SQLAlchemy & Alembic Database Skills

## 1. Purpose
Defines database engineering guidelines, SQLAlchemy 2.0 ORM patterns, safe transaction bounds, explicit model structures, and Alembic schema migration policies in SilverPilot.

## 2. Rules
- **N+1 Avoidance:** Eagerly load all relationship attributes accessed in loops or collections using `selectinload` (for collections) or `joinedload` (for one-to-one/many-to-one). Never allow implicit lazy loading in production request paths.
- **Explicit ORM Relationships:** Define relationships using SQLAlchemy `relationship()` with exact `back_populates` mapping.
- **Indexes & Constraints:** Apply database indexes (`index=True`) on fields frequently queried (e.g. symbols, dates, hashes) and unique constraints to prevent duplicates.
- **Alembic Determinism:** Every migration must be generated cleanly. Auto-generated migrations must be hand-reviewed, and must contain explicit `upgrade()` and `downgrade()` steps.
- **Rollback Safety:** DB sessions must be properly managed using async context managers or DI context, ensuring automatic rollback on exceptions.
- **PostgreSQL Compatibility:** Do not write SQLite-only statements or non-standard SQL if it breaks compatibility with the production PostgreSQL server.

## 3. Recommended Patterns
- Use SQLAlchemy 2.0 style queries (e.g. `select(Model).where(...)`).
- Run schema audits prior to writing migration files to evaluate changes against existing tables.
- Define appropriate foreign keys with `ondelete="CASCADE"` or `ondelete="SET NULL"` guidelines.

## 4. Anti-Patterns
- **Implicit Lazy Loads:** Fetching a parent model, iterating through children without eager loading, causing dozens of database sub-queries.
- **Destructive Auto-Migration:** Blindly running `alembic revision --autogenerate` without manually inspecting the generated python script (often drops constraints or mislabels columns).
- **Bypassing Alembic:** Mutating production database schemas manually without a corresponding Alembic migration.

## 5. Checklist
- [ ] Are relationships eagerly loaded (`selectinload`/`joinedload`) to prevent N+1 queries?
- [ ] Is `back_populates` defined on both ends of all relationships?
- [ ] Do foreign keys and search columns have proper indexes?
- [ ] Does the Alembic migration script have both `upgrade()` and `downgrade()` filled out?
- [ ] Have you verified query compatibility against PostgreSQL structures?

## 6. Example Guidance
```python
# SQLAlchemy Model definition
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base

class Portfolio(Base):
    __tablename__ = "portfolios"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_name: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Eager relationship definition
    trades: Mapped[list["Trade"]] = relationship(
        back_populates="portfolio", 
        cascade="all, delete-orphan"
    )

class Trade(Base):
    __tablename__ = "trades"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    
    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")

# Query pattern avoiding N+1
async def get_portfolio_with_trades(session: AsyncSession, portfolio_id: int) -> Portfolio | None:
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.trades))  # Eager collection load
        .where(Portfolio.id == portfolio_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```
