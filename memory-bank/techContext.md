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

## Infrastructure Access

- VPS access method: SSH alias `silverpilot-vps`.
- Usage: `ssh silverpilot-vps`.
- Current project path on VPS: `/opt/silverpilot/SilverPilot`.
- Runtime target: Ubuntu VPS with Docker installed.
- Agents must not read or expose SSH private keys or production secrets.
- Runtime secrets belong in VPS-local `.env.production`, not in markdown or git.

## Phase 1 Backend Runtime

- API container uses Python 3.12.
- FastAPI serves the backend.
- SQLAlchemy 2.x owns ORM models.
- Alembic owns database migrations.
- PostgreSQL runs through Docker Compose.
- PostgreSQL is private to the Compose network by default.
- Initial endpoints are deterministic and do not require LLM providers.
- Token/cost discipline remains deferred to the LLM gateway phase; current backend must work without LLM availability.
