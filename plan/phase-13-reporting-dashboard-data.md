# Phase 13: Reporting Dashboard Data

## ROADMAP Objective

Expose portfolio, PnL, risk, and health data for future clients. Phase 13 is a
backend JSON contract only; it does not add dashboard UI.

## Current Evidence

- `src/silverpilot/app/api/schemas.py` defines account dashboard report DTOs:
  portfolio, position valuation, PnL, risk, health, and combined response.
- `src/silverpilot/app/api/services.py` adds
  `ApiQueryService.get_account_dashboard_report`.
- `src/silverpilot/app/api/routes.py` exposes
  `GET /api/v1/reports/accounts/{account_id}/dashboard`.
- `tests/test_api_phase10.py` verifies the endpoint contract against an
  isolated in-memory database.

## Required Interfaces And Schema

- `AccountDashboardReportResponse`
  - `account`
  - `portfolio`
  - `pnl`
  - `risk`
  - `health`
- Portfolio valuation fields:
  - cash available/reserved
  - position market value
  - total value
  - realized/unrealized/net PnL
  - return percentage
  - per-position valuation status
  - indicative pricing note
- Risk summary fields:
  - pending intent count
  - approve/reduce/reject counts
  - latest decision timestamp
  - rejection reason counts

## Data Flow

Clients call the read-only account dashboard report endpoint. The route
delegates to `ApiQueryService`. The service loads the account, wallets,
positions, latest quotes, trades, and risk decisions using ORM queries, then
maps them into Pydantic DTOs. The report does not persist snapshots or mutate
wallets, positions, trades, risk decisions, orders, or backtests.

## Failure Modes

- Missing account id returns the standard structured `404`.
- Missing latest quote for a position produces `valuation_status=missing_quote`.
- Stale latest quote for a position produces `valuation_status=stale_quote`.
- Any non-valued position degrades account health instead of fabricating a
  valuation.
- Public bank quote valuation is explicitly labeled as indicative.

## Exact Tests

- `pytest tests/test_api_phase10.py`
- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy`

## Done Gate

PASS when future clients can consume one stable JSON contract for account,
portfolio, PnL, risk, and health; valuation uses fresh bank buy prices for
indicative liquidation value; stale/missing prices are surfaced; and full
verification is green.

## Out Of Scope

- Dashboard UI.
- Persisted report records or scheduled report generation.
- Authentication/authorization.
- Live quote fetching.
- ML experiments.
- Real-money execution.
