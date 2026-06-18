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

- `db`: Postgres 16 with a named `postgres_data` volume and loopback-bound host
  port.
- `migrate`: one-shot Alembic migration service. It must complete before `api`
  starts.
- `api`: FastAPI service exposing `/health` on a loopback-bound host port.
- `collector`: optional profile for bounded Kuveyt Turk quote collection. It is
  not an always-on scheduler.

Telegram is still an optional notification adapter. Enabling Telegram requires
`SILVERPILOT_TELEGRAM_ENABLED=true`, a bot token, and a chat id in the runtime
environment. Bot polling, webhooks, and remote command handling are not part of
the current system.

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
```

Collector success must be verified from bounded collector JSON output or
database state, not from Telegram messages.

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
