# Codex Framework Migration Map

Date: 2026-06-03

This file documents `.codex/` hardening migrations so old framework files are not silently deleted.

## Skill layout migration

Reason: root-level `.codex/skills/*.md` files looked like official Codex skills but were not official directory-based `SKILL.md` bundles. They were migrated to Codex-local bundles under `.codex/skills/<skill-name>/SKILL.md`.

Official auto-discovery caveat: within the user's `.codex/`-only boundary, these are Codex-local skill bundles/playbooks, not guaranteed official auto-discovered Codex skills.

| Old file | New location | Behavior preserved |
| --- | --- | --- |
| `.codex/skills/alembic-migrations.md` | `.codex/skills/alembic-migrations/SKILL.md` | Yes, merged with migration-safety guidance. |
| `.codex/skills/alembic-migration-safety.md` | `.codex/skills/alembic-migrations/SKILL.md` | Yes, consolidated. |
| `.codex/skills/docker-compose-ops.md` | `.codex/skills/docker-compose-ops/SKILL.md` | Yes, merged with Docker verification guidance. |
| `.codex/skills/docker-compose-verification.md` | `.codex/skills/docker-compose-ops/SKILL.md` | Yes, consolidated. |
| `.codex/skills/fastapi-sqlalchemy.md` | `.codex/skills/fastapi-sqlalchemy/SKILL.md` | Yes, condensed. |
| `.codex/skills/financial-agent-runtime.md` | `.codex/skills/financial-agent-runtime/SKILL.md` | Yes, condensed. |
| `.codex/skills/paper-trading-risk.md` | `.codex/skills/financial-risk-regression/SKILL.md` | Partially; paper-trading risk rules merged into broader risk regression bundle. |
| `.codex/skills/financial-risk-regression.md` | `.codex/skills/financial-risk-regression/SKILL.md` | Yes, consolidated. |
| `.codex/skills/git-safe-operations.md` | `.codex/skills/git-safe-operations/SKILL.md` | Yes. |
| `.codex/skills/github-actions-monitoring.md` | `.codex/skills/github-actions-monitoring/SKILL.md` | Yes. |
| `.codex/skills/integration-testing.md` | `.codex/skills/integration-testing/SKILL.md` | Yes. |
| `.codex/skills/pytest-fastapi.md` | `.codex/skills/pytest-fastapi/SKILL.md` | Yes. |
| `.codex/skills/streamlit-dashboard.md` | `.codex/skills/streamlit-dashboard/SKILL.md` | Yes, merged with smoke-testing guidance. |
| `.codex/skills/streamlit-smoke-testing.md` | `.codex/skills/streamlit-dashboard/SKILL.md` | Yes, consolidated. |
| `.codex/skills/testing-verification.md` | `.codex/workflows/aggressive-validation.md`, `.codex/skills/pytest-fastapi/SKILL.md`, `.codex/skills/integration-testing/SKILL.md` | Replaced by stronger validation workflow and test bundles. |

## Workflow migration

Reason: older workflow names overlapped with the newer release-gate framework. They are intentionally replaced by more explicit workflows.

| Old file | Replacement | Behavior preserved |
| --- | --- | --- |
| `.codex/workflows/deployment-diagnosis.md` | `.codex/workflows/deploy-readiness.md`, `.codex/workflows/post-deploy-verification.md`, `.codex/workflows/rollback-response.md` | Yes, split by phase. |
| `.codex/workflows/release-readiness.md` | `.codex/workflows/release-gate.md` | Yes, stricter gate. |
| `.codex/workflows/safe-implementation.md` | `.codex/agents/implementation-worker.toml`, `.codex/workflows/aggressive-validation.md`, `.codex/workflows/commit-readiness.md` | Yes, split into implementation and verification gates. |

## Codex-only routing migration

Reason: the root `AGENTS.md` previously pointed Codex users at `.agent/` Antigravity/Gemini governance, agents, skills, workflows, and memory files. That created conflicting routing, model, RTK, and commit/push policies. Root `AGENTS.md` is now only a framework router; Codex-specific instructions live in `.codex/AGENTS.md`.

| Old authority | New Codex authority | Behavior preserved |
| --- | --- | --- |
| `.agent/GEMINI.md` for Codex task governance | `.codex/AGENTS.md`, `.codex/README.md`, `.codex/workflows/codex-orchestration.md` | Partially; Codex approval gates now override automatic commit/push language. |
| `.agent/workflows/orchestrate.md` for subagent/model routing | `.codex/workflows/codex-orchestration.md` | Yes, translated to Codex agent names and model tiers. |
| `.agent/agents/*.md` coding roles | `.codex/agents/*.toml` | Yes, mapped to Codex TOML agents. |
| `.agent/skills/*.md` technical rules | `.codex/skills/<skill-name>/SKILL.md` | Yes where local Codex skill bundles exist. |
| `.agent/memory/*.md` as Codex memory source | `.codex/memory/*.md` | Yes for Codex validation/release policies. |

## Duplicate cleanup

- `docker-compose-verification` merged into `docker-compose-ops`.
- `alembic-migration-safety` merged into `alembic-migrations`.
- `streamlit-smoke-testing` merged into `streamlit-dashboard`.
- `paper-trading-risk` merged into `financial-risk-regression`.
- `release-readiness` replaced by `release-gate`.
- `safe-implementation` replaced by implementation-worker plus validation/commit gates.
- Root `AGENTS.md` is now a neutral router; `.codex/AGENTS.md` routes Codex work to `.codex/` only.
