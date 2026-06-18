# Phase 1 Audit: Domain Model And Database

## ROADMAP Objective

Implement first-class domain concepts and PostgreSQL-ready schema with
SQLAlchemy models, Alembic baseline, relationships, and constraint tests. Do
not include trading strategies.

## Current Evidence

- `src/silverpilot/app/domain/models.py` defines immutable Pydantic domain
  shapes for users, accounts, instruments, quotes, bars, and indicators.
- `src/silverpilot/app/domain/value_objects.py` provides Decimal-safe money and
  parsing helpers.
- `src/silverpilot/app/domain/enums.py` centralizes domain enums.
- `src/silverpilot/app/db/models.py` defines normalized tables for currencies,
  metals, units, banks, instruments, accounts, wallets, quotes, bars, and
  indicator snapshots.
- `migrations/versions/20260617_0001_initial_core_schema.py` is the baseline
  Alembic migration.
- `tests/test_domain_models.py` and `tests/test_database_schema.py` verify
  validation, relationships, indexes, and constraints.

## Required Interfaces And Schema

Keep money and quantity fields as database `Numeric` values and Python
`Decimal` values. Maintain normalized identities for banks, metals, currencies,
units, execution venues, reference instruments, execution instruments,
instrument mappings, accounts, wallets, quotes, bars, and indicators.

## Data Flow

Domain DTOs validate financial values at the service boundary. SQLAlchemy
models persist normalized entities and enforce critical constraints such as
non-negative balances, valid time windows, unique instrument mappings, and bank
sell price greater than or equal to bank buy price.

## Failure Modes

- Float usage in money or quantity paths.
- Schema constraints missing for financial invariants.
- Alembic migration drift from SQLAlchemy metadata.
- User/account/instrument identities becoming denormalized.
- Relationship or uniqueness gaps that allow duplicate execution instruments.

## Exact Tests

- `pytest tests/test_domain_models.py tests/test_database_schema.py`
- Apply and downgrade the baseline migration in a local database when a real
  PostgreSQL target is available.
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

Domain validation and schema tests pass, the migration applies cleanly, and no
strategy, signal, order, broker, or backtest behavior exists in Phase 1.

## Out Of Scope

- Provider implementation.
- Price collection.
- Indicator calculation.
- Strategy, risk, broker, ledger, backtest, API, Telegram, ML, Hermes.
