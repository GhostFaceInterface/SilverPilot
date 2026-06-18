# Phase 10: REST API

## ROADMAP Objective

Expose backend state as JSON for future Telegram, web, and mobile clients.
Phase 10 is a read-only REST API boundary over the Phase 0-9 backend state.

## Current Evidence

- `src/silverpilot/app/api/schemas.py` defines response DTOs for health,
  pagination, accounts, wallets, banks, execution instruments, prices,
  indicators, regimes, paper trades, positions, backtests, and reports.
- `src/silverpilot/app/api/services.py` adds `ApiQueryService`, keeping SQL
  access and pagination outside route handlers.
- `src/silverpilot/app/api/routes.py` exposes versioned `/api/v1` endpoints.
- `src/silverpilot/app/main.py` includes the API router and preserves `/health`.
- `tests/test_api_phase10.py` verifies JSON responses against an isolated
  in-memory database with dependency overrides.

## Required Interfaces And Schema

- `GET /api/v1/health`
- `GET /api/v1/system/health`
- `GET /api/v1/accounts`
- `GET /api/v1/accounts/{account_id}`
- `GET /api/v1/accounts/{account_id}/wallets`
- `GET /api/v1/banks`
- `GET /api/v1/instruments/execution`
- `GET /api/v1/prices/latest`
- `GET /api/v1/indicators/latest`
- `GET /api/v1/regimes/latest`
- `GET /api/v1/trades`
- `GET /api/v1/positions`
- `GET /api/v1/backtests`
- `GET /api/v1/backtests/{run_id}`
- `GET /api/v1/reports/backtests/{run_id}`

List endpoints return pagination metadata. Missing single resources return a
structured `404` payload.

## Data Flow

Client calls a versioned route. The route validates HTTP query/path inputs,
obtains a SQLAlchemy session through FastAPI dependency injection, and delegates
to `ApiQueryService`. The service runs read-only ORM queries and maps rows into
Pydantic response DTOs. No router contains financial formulas, broker behavior,
risk evaluation, strategy logic, or backtest replay logic.

## Failure Modes

- Missing account or backtest id returns structured `404`.
- Invalid UUIDs and pagination values are rejected by FastAPI validation.
- Empty collections return `items: []` with zero pagination totals.
- Database/session failures are left observable as server errors; no silent
  fallback fabricates financial state.

## Exact Tests

- `pytest tests/test_api_phase10.py`
- `pytest tests/test_health.py`
- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

PASS when the API exposes the Phase 10 read resources through `/api/v1`,
response schemas serialize money/time/UUID fields correctly, route handlers stay
thin, schema tests pass against an isolated test database, and the full
verification matrix is green.

## Out Of Scope

- Mutating order/trade/backtest endpoints.
- Authentication, authorization, account ownership checks, CORS policy, rate
  limiting, and audit logs for remote SaaS exposure.
- Telegram adapter.
- Dashboard/frontend-specific business logic.
- Real-money execution.
- Hermes, ML, or news/event-risk behavior.
