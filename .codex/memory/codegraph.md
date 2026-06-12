# SilverPilot Local Codegraph

This is the local, short CodeGraph substitute for Codex scout work. Keep it
current and compact; do not install an external codegraph tool for this purpose.

## Canonical Docs

- `AGENTS.md`: root router between Codex `.codex/` and Antigravity `.agent/`.
- `.codex/AGENTS.md`: Codex agent, skill, workflow, and RTK index.
- `.codex/README.md`: Codex framework boundaries, model policy, validation, and approvals.
- `.codex/workflows/codex-orchestration.md`: first routing workflow.
- `docs/ARCHITECTURE.md`, `docs/PHASE_PLAN.md`, and risk/contract docs when app behavior changes.

## App Entrypoints

- FastAPI app and routers: `apps/api/app/`.
- Runtime financial/data agents: `apps/api/app/agents/`.
- Dashboard app: `apps/dashboard/`.
- Database and migrations: `apps/api/alembic/`, `apps/api/app/models/`, and service/data-access modules under `apps/api/app/`.
- Tests: `tests/`, `apps/api/tests/`, and any subsystem-local test roots discovered by `rg --files`.

## Codex Framework Entrypoints

- Agent definitions: `.codex/agents/*.toml`.
- Local skills: `.codex/skills/<skill-name>/SKILL.md`.
- Workflows: `.codex/workflows/*.md`.
- Verifier: `.codex/scripts/verify-agent-framework.py`.

## Skill Routing Hints

- FastAPI, services, SQLAlchemy: `fastapi-sqlalchemy`.
- Alembic/schema/data-loss risk: `alembic-migrations` plus escalation for high risk.
- Runtime agents, API tokens, paper-trading boundaries: `financial-agent-runtime`.
- LLM gateway, traces, token/cost budgets: `llm-observability-budget`.
- Collectors, source priority, freshness, parser failures: `collector-data-pipeline`.
- ML inference, backtests, datasets: `ml-backtest-dataset`.
- Docs and README drift: `documentation-consistency`.
- Tests and smoke checks: `pytest-fastapi`, `integration-testing`, `docker-compose-ops`, `financial-risk-regression`.

## Scout Read-First Paths

1. Read this file and the relevant canonical docs above.
2. Use targeted `rg -n` for the requested symbol, route, model, workflow, or doc phrase.
3. Read only line ranges needed for evidence.
4. Hand off using `.codex/workflows/context-handoff.md`.
