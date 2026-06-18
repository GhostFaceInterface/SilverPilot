# Deployment Readiness Before Phase 14

## Objective

Put the project on deployable foundations before ML experiments begin.
`ROADMAP.md` remains the canonical product plan; this file records the
deployment-readiness gate inserted between Phase 13 and Phase 14.

## Current Status

Phase 0-13 is implemented and locally verified. Phase 14 is still the next
product phase, but deployment readiness is now required before starting it.

## Deliverables

- `Dockerfile` for the FastAPI backend image.
- `docker-compose.yml` with Postgres, one-shot Alembic migrations, API, and an
  optional bounded collector profile.
- `.dockerignore` to keep secrets, caches, local databases, and generated files
  out of the image context.
- `.env.example` with non-secret placeholders for Postgres, API port, Telegram,
  and collector runtime settings.
- `docs/deployment.md` with local gate, migration gate, health checks, rollback,
  and remote approval rules.
- `.codex/scripts/verify-docker.sh` aligned with the actual Compose services.

## Done Gate

PASS when local tests, lint, typing, Docker Compose config validation, and
deployment documentation checks pass without requiring a VPS connection.

## Explicitly Out Of Scope

- Remote deployment to `silverpilot-vps`.
- CD automation.
- Telegram bot polling or webhooks.
- Real-money execution.
- Production secret inspection.
- Phase 14 ML implementation.
