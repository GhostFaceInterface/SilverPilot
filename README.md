# SilverPilot

SilverPilot is a paper-trading and analysis system for silver scenarios using a virtual 600 USD starting balance.

## Scope

- No real-money trading.
- No bank automation.
- No live buy/sell execution.
- Data first, simulation second, risk policy third, LLM agents later, ML last.

## Current Phase

Phase 1 backend core is implemented locally. VPS pull and production env validation are pending.

## Canonical Sources

- Project purpose: `memory-bank/projectbrief.md`
- Current state: `memory-bank/activeContext.md`
- Milestones: `memory-bank/progress.md`
- Architecture: `docs/ARCHITECTURE.md`
- Decisions: `docs/DECISIONS.md`
- Data contracts: `docs/DATA_CONTRACTS.md`
- Risk rules: `docs/RISK_POLICY.md`
- Work log: `docs/WORKLOG.md`
- Agent boundaries: `memory-bank/agentRules.md` and `agents/*.md`

## First Validation Rules

- Keep documentation short.
- Do not duplicate canonical information.
- Do not add secrets.
- Do not add real banking integration.
- Do not add real-money execution.

## Next Work

Next deployment task:

- Commit and push Phase 1.
- Pull the latest repo state on the VPS.
- Create VPS-local `.env.production` from `.env.example` if missing.
- Fill production secret values manually on the VPS.
- Run `docker compose --env-file .env.production config`.

## Local Validation

```bash
docker compose up -d postgres
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl -fsS http://127.0.0.1:8000/health
```
