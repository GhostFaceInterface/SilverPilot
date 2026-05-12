# SilverPilot

SilverPilot is a paper-trading and analysis system for silver scenarios using a virtual 600 USD starting balance.

## Scope

- No real-money trading.
- No bank automation.
- No live buy/sell execution.
- Data first, simulation second, risk policy third, LLM agents later, ML last.

## Current Phase

Phase 2 paper-trading engine is in progress.

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

Next implementation task:

- Deploy Phase 2 code to the VPS.
- Rebuild the API container.
- Run a paper-trade smoke test against the VPS.

## Local Validation

```bash
docker compose up -d postgres
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/paper-trades/position
```

## VPS Validation

```bash
ssh silverpilot-vps
cd /opt/silverpilot/SilverPilot
docker compose --env-file .env.production ps
curl -fsS http://127.0.0.1:8000/health
```
