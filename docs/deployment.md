# Deployment Readiness

This document defines the safe path from local verification to a VPS Docker
Compose deployment. It does not authorize deployment by itself.

## Target

- Environment: `staging` or `production`, named before execution.
- Host: the VPS reached through `ssh silverpilot-vps`, only after explicit user
  approval.
- Version: a committed Git SHA or tagged release, named before execution.

## Local Gate

Run these commands before any remote action:

```bash
pytest -q
ruff check .
ruff format --check .
mypy
bash .codex/scripts/verify-docker.sh
```

If Docker is available locally, also run:

```bash
bash .codex/scripts/verify-docker.sh --build
```

## Compose Services

- `postgres`: Postgres 16 with a named `postgres_rebuild_data` volume and
  loopback-bound host port. The rebuild volume name intentionally avoids
  mutating legacy pre-reset database volumes during the first deployment.
- `migrate`: one-shot Alembic migration service. It must complete before `api`
  starts.
- `api`: FastAPI service exposing `/health` on a loopback-bound host port.
- `worker`: always-on paper-trading runtime. It uses seeded paper account ids
  and never calls real-money bank execution.
- `collector`: optional profile for bounded Kuveyt Turk quote collection. It is
  retained for one-shot checks; the normal live paper flow runs through
  `worker`.
- `telegram`: optional `telegram` profile for read-only status commands and
  alerts. It must never initiate trades.

Telegram is still an optional notification adapter. Enabling Telegram requires
`SILVERPILOT_TELEGRAM_ENABLED=true`, a bot token, and a chat id in the runtime
environment. The bot command surface is read-only: `/health`, `/prices`,
`/portfolio`, `/trades`, `/risk`, and `/help`.

## Paper Runtime Bootstrap

Before enabling `worker`, run the idempotent bootstrap in the target Compose
environment:

```bash
docker compose run --rm api silverpilot-bootstrap-paper
```

Record the returned `account_id`, `bank_instrument_id`,
`execution_instrument_id`, and `strategy_id` in the target environment as
`SILVERPILOT_RUNTIME_ACCOUNT_ID`,
`SILVERPILOT_RUNTIME_BANK_INSTRUMENT_ID`,
`SILVERPILOT_RUNTIME_EXECUTION_INSTRUMENT_ID`, and
`SILVERPILOT_RUNTIME_STRATEGY_ID`. Bootstrap must not reset an existing wallet
balance.

## Migration Gate

Before deploying a version with database changes:

1. Review new Alembic revisions.
2. Confirm the target database has a restorable backup.
3. Run `alembic upgrade head` through the `migrate` service.
4. Block deployment if migration failure would leave financial state ambiguous.

## Health Checks

Required checks after container startup:

```bash
curl -fsS http://127.0.0.1:${SILVERPILOT_API_PORT:-8000}/health
curl -fsS http://127.0.0.1:${SILVERPILOT_API_PORT:-8000}/api/v1/health
curl -fsS http://127.0.0.1:${SILVERPILOT_API_PORT:-8000}/api/v1/system/health
```

Runtime success must be verified from `/api/v1/system/health`, runtime tick
rows, and database state, not from Telegram messages.

## Rollback

Rollback requires:

- previous known-good image or Git SHA,
- database backup status,
- command to stop the new services,
- command to restart the previous version,
- post-rollback `/health` check.

Do not roll back database migrations that touched financial state unless a
reviewed data restore plan exists.

## Remote Deployment

Remote deploy commands, SSH sessions, service restarts, and production smoke
checks require explicit user approval.

Do not print `.env` contents or secret values.
