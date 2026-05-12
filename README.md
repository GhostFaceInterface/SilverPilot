# SilverPilot

SilverPilot is a paper-trading and analysis system for silver scenarios using a virtual 600 USD starting balance.

## Scope

- No real-money trading.
- No bank automation.
- No live buy/sell execution.
- Data first, simulation second, risk policy third, LLM agents later, ML last.

## Current Phase

Phase 3 scheduled collector execution is being deployed.

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

- Deploy collector runner and health visibility to the VPS.
- Validate `GET /collectors/health`.
- Keep collector profile opt-in until real provider config is selected.

## Local Validation

```bash
docker compose up -d postgres
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/paper-trades/position
curl -fsS http://127.0.0.1:8000/collectors/runs/latest
curl -fsS http://127.0.0.1:8000/collectors/health
curl -fsS http://127.0.0.1:8000/prices/latest
```

Optional collector runner:

```bash
docker compose --profile collector up -d collector
```

## VPS Validation

```bash
ssh silverpilot-vps
cd /opt/silverpilot/SilverPilot
docker compose --env-file .env.production ps
curl -fsS http://127.0.0.1:8000/health
```
