# Tech Context

## Planned Backend Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- httpx
- tenacity
- Docker Compose

## Planned Data Stack

- Pandas
- Polars
- DuckDB
- NumPy

## Planned LLM Stack

- OpenRouter first.
- LiteLLM later if routing, fallback, or budget proxying is needed.
- Langfuse before production agent usage.
- Instructor/Pydantic for structured output validation.

## Planned ML Stack

- LightGBM first.
- MLflow for model registry.
- AutoGluon/Chronos-Bolt only after baseline ML exists.
- Feast is optional and deferred.

## Phase 0 Constraint

No package installation is required yet. Dependency locking starts in Phase 1.

