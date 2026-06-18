# Phase 0 Audit: Repository Skeleton

## ROADMAP Objective

Create a clean Python backend skeleton with `pyproject.toml`, FastAPI app,
settings module, domain model starting point, and tests. No trading logic,
Docker, database providers, Telegram, ML, or Hermes.

## Current Evidence

- `pyproject.toml` defines package metadata, dependencies, pytest, ruff, and
  mypy configuration.
- `.github/workflows/ci.yml` runs the project validation gates.
- `src/silverpilot/app/main.py` exposes the FastAPI app and health endpoint.
- `src/silverpilot/app/core/settings.py` defines environment-backed settings.
- `.env.example` documents the expected local configuration surface.
- `tests/test_health.py` verifies the app health behavior.

## Required Interfaces And Schema

Phase 0 requires only a stable importable app boundary and configuration
surface. No database schema or financial contracts are required in this phase.

## Data Flow

Client or test code imports the FastAPI app, calls the health endpoint, and
receives a JSON status response. Settings are loaded from environment values.

## Failure Modes

- App import failure.
- Missing or invalid settings defaults.
- CI drift between local tooling and workflow commands.
- Health endpoint returning non-JSON or unstable shape.

## Exact Tests

- `pytest tests/test_health.py`
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

The app imports, health test passes, and static validation passes without any
trading, provider, scheduler, Telegram, ML, or Docker behavior.

## Out Of Scope

- Database schema.
- Bank scraping or provider logic.
- Trading strategies or signals.
- Telegram, dashboard, ML, Hermes, deployment.
