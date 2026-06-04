# Deploy Readiness Workflow

## Purpose
Decide whether a change is ready for staging or production deployment.

## When to use
- Before Docker Compose deployment.
- Before VPS smoke workflow dispatch.
- Before any production/staging action.

## Agents involved
- `deploy_guardian`
- `rollback_planner`
- `security_reviewer`
- `test_verifier`
- `final_reviewer`

## Required inputs
- Deployment target and environment.
- Commit SHA or branch.
- Local and CI verification evidence.
- Migration and rollback plan.
- Health check URLs or commands.

## Read-only phase
1. Inspect Docker Compose, Dockerfiles, health checks, ports, volumes, and env assumptions.
2. Inspect Alembic migration risk without mutating the database.
3. Confirm model/data artifact availability assumptions.
4. Confirm rollback path and previous known-good version.

## Implementation phase
No deployment or production mutation occurs in this workflow. Required fixes return to implementation and validation.

## Verification phase
- Run `.codex/scripts/verify-docker.sh`.
- Run local tests and CI status checks.
- Run migration safety review for Alembic changes.
- Confirm rollback plan exists.

## Failure handling
- Block deploy if Docker config/build is unverified, migration risk is unresolved, secrets are exposed, target is ambiguous, or rollback is missing.

## Stop conditions
- Production database mutation without approved migration plan.
- Unknown deploy target.
- Health endpoint unavailable before deploy.
- Required secrets missing or accidentally printed.

## Approval requirements
- Do not run deployment commands, SSH deploys, workflow dispatches, or production smoke commands without explicit user approval.

## Expected output format
1. Deploy readiness: PASS / FAIL / UNKNOWN.
2. Target and version.
3. Pre-deploy evidence.
4. Migration/data/model risks.
5. Rollback plan summary.
6. Proposed deploy command requiring approval.
