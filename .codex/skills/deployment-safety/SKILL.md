---
name: "deployment-safety"
description: "Codex-local skill bundle for deploy readiness, rollback readiness, and production-action guardrails."
---

# Deployment Safety

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Use When
- Preparing deploy readiness, post-deploy checks, or rollback plans.
- Reviewing Docker, env, DB migration, model artifact, or health-check assumptions.

## Rules
- Read-only until explicit user approval.
- The deployment target and version must be named before any action.
- Do not print secrets or inspect secret values.
- Deployment, rollback, SSH, workflow dispatch, production smoke checks, and production logs require explicit user approval.
- Block deploy if runtime verification, migration safety, rollback readiness, or target identity is UNKNOWN.

## Evidence
- Target environment and version.
- Docker/config validation.
- Migration/data/model artifact risk.
- Health-check plan.
- Rollback trigger and rollback command proposal.
