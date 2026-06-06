# SilverPilot

SilverPilot is a paper-trading and analysis system for silver scenarios using a virtual 600 USD starting balance.

## Scope

- No real-money trading.
- No bank automation.
- No live buy/sell execution.
- Data first, simulation second, risk policy third, LLM agents later, ML last.

## Current Phase

Core implementation follows `docs/PHASE_PLAN.md` first. `docs/ROADMAP.md` is legacy context only and must not be used for current phase routing.

Current official phase is Phase 3 closeout before Strategy V2 and trade intents. Multi-timeframe storage exists, but runtime hardening still needs to enforce `1d -> 1h -> 5m`, fail closed on stale/misaligned data, and keep agent/ML expansion frozen until Phase 5 completes.

## Canonical Sources

- Current implementation authority: `docs/PHASE_PLAN.md`
- Codex execution framework: `.codex/README.md`
- Codex routing and release rules: `.codex/AGENTS.md`
- Architecture: `docs/ARCHITECTURE.md`
- Decisions: `docs/DECISIONS.md`
- Data contracts: `docs/DATA_CONTRACTS.md`
- Risk rules: `docs/RISK_POLICY.md`
- Work log: `docs/WORKLOG.md`
- Framework router: `AGENTS.md`

## First Validation Rules

- Keep documentation short.
- Do not duplicate canonical information.
- Prefer updating an existing canonical markdown file instead of creating a new one.
- Do not add secrets.
- Do not add real banking integration.
- Do not add real-money execution.

## Next Work

Next implementation task:

- Close Phase 3 in runtime consumption, not only storage.
- Enforce deterministic Strategy V2 on `1d` trend plus `1h` entry inputs.
- Require trade intents between strategy and paper execution before further agent/ML expansion.

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
docker compose run --rm api python -m app.collectors.runner --job global-xag-usd
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
