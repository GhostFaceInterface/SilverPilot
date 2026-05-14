# SilverPilot

SilverPilot is a paper-trading and analysis system for silver scenarios using a virtual 600 USD starting balance.

## Scope

- No real-money trading.
- No bank automation.
- No live buy/sell execution.
- Data first, simulation second, risk policy third, LLM agents later, ML last.

## Current Phase

Phase 3.4 sustained collector validation is running on the VPS. Execution-critical Kuveyt Türk public bank silver pricing has passed smoke validation, and Phase 4 must wait until `/collectors/validation-gate` allows it.

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

- Review sustained collector freshness, failures, duplicates, and missing-run ratio.
- Keep Phase 4 blocked until `/collectors/validation-gate` reports `phase4_allowed: true`.
- If the gate remains degraded after enough runtime, fix the specific gate reasons before adding the risk engine.

## Local Validation

```bash
.venv/bin/python -m pytest apps/api/tests
docker compose --profile collector config
docker compose up -d postgres
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/paper-trades/position
curl -fsS http://127.0.0.1:8000/collectors/runs/latest
curl -fsS http://127.0.0.1:8000/collectors/health
curl -fsS "http://127.0.0.1:8000/collectors/quality?window_hours=24&expected_interval_minutes=15"
curl -fsS "http://127.0.0.1:8000/collectors/validation-gate?window_hours=24&expected_interval_minutes=15&stale_after_minutes=60"
curl -fsS http://127.0.0.1:8000/prices/latest
```

Optional collector runner:

```bash
docker compose --profile collector up -d collector
docker compose run --rm api python -m app.collectors.runner --job kuveyt-silver
docker compose run --rm api python -m app.collectors.runner --job stooq-xag-usd
docker compose run --rm api python -m app.collectors.runner --job tcmb-usd-try
docker compose run --rm api python -m app.collectors.runner --job fed-rss
docker compose run --rm api python -m app.collectors.runner --job fred-macro
```

## CI/CD

GitHub Actions runs backend tests, Docker Compose config validation, and API image build on push and pull request.

Manual VPS smoke validation is available from GitHub Actions with `workflow_dispatch` after repository secrets are configured.

Required repository secrets:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_KEY`

Optional repository secrets:

- `VPS_PORT`
- `VPS_KNOWN_HOSTS`
- `VPS_PROJECT_PATH`

## VPS Validation

```bash
ssh silverpilot-vps
cd /opt/silverpilot/SilverPilot
docker compose --env-file .env.production ps
curl -fsS http://127.0.0.1:8000/health
```
