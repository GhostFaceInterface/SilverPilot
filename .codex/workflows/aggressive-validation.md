# Aggressive Validation Workflow

## Purpose
Enforce the SilverPilot rule: work is not complete until verification evidence exists.

## When to use
- Before claiming any implementation is finished.
- Before commit, push, deploy, release, or production incident closeout.
- After changes to runtime code, tests, Docker, CI/CD, database models, Alembic migrations, Streamlit, financial/risk math, collectors, or deployment scripts.

## Agents involved
- `test_strategist`: read-only validation plan.
- `test_verifier`: executes and classifies test evidence.
- `security_reviewer`: read-only secret, auth, workflow, and supply-chain review.
- `final_reviewer`: independent gate decision.
- `implementation_worker`: only for approved fixes found during validation.

## Required inputs
- Change summary and changed files.
- Reproduction steps or target behavior.
- Known risk areas.
- Available local commands and CI workflow names.

## Read-only phase
1. Inspect git status and diff summary.
2. Map changed files to affected runtime/test/deploy paths.
3. Identify applicable validation levels.
4. Check for secrets, generated artifacts, database dumps, and model binaries in the diff.

## Implementation phase
Only `implementation_worker` may write files, and only after the failed evidence is understood and a minimal fix is approved.

## Verification phase
Run the highest applicable level. Lower levels are prerequisites unless explicitly not applicable.

Concrete local entrypoints:
- `bash .codex/scripts/verify-local.sh` for static sanity, pytest, and Compose config.
- `bash .codex/scripts/verify-tests.sh` for pytest-only verification.
- `bash .codex/scripts/verify-docker.sh` for Compose config.
- `bash .codex/scripts/verify-docker.sh --build` for local image build when Docker daemon is available.
- `bash .codex/scripts/verify-ci-status.sh` for read-only CI status when `gh` is authenticated.
- `bash .codex/scripts/verify-post-deploy.sh <base-url>` for approved read-only health checks.

### Level 0 - Static sanity
- Formatting/lint/import checks where available.
- Syntax checks.
- No obvious missing imports.
- No accidental secrets or unsafe generated artifacts.

### Level 1 - Unit tests
- Targeted pytest for changed modules.
- Failure reproduction test when fixing a bug.
- Changed-module tests.

### Level 2 - Integration tests
- API route tests.
- Service/database interaction tests.
- Collector/pipeline interaction tests.
- Dashboard smoke tests where possible.

### Level 3 - Runtime verification
- `docker compose config`.
- Docker Compose build when runtime/container behavior changed.
- Docker Compose up for relevant services when safe.
- Health checks and logs scanned for exceptions.
- `scripts/verify_execution_pipeline.py` when trading pipeline behavior changed.

### Level 4 - CI/CD verification
- GitHub Actions workflow status.
- Failed job log analysis.
- Artifact/log inspection.
- No red workflows ignored.

### Level 5 - Post-deploy verification
- Staging/production health check with explicit approved target.
- Service logs.
- Critical user flow smoke check.
- Rollback readiness.

### Level 6 - Release gate
- `final_reviewer` approval.
- `security_reviewer` approval.
- Rollback plan exists.
- Known risks documented.
- Explicit user approval for push/deploy.

## Failure handling
- Classify every failure as test failure, environment failure, missing dependency, unavailable external service, or insufficient evidence.
- Do not relabel a failed or skipped test as passed.
- Do not proceed to commit/push/deploy while required evidence is failed or unknown.

## Stop conditions
- Secret exposure or credential leak risk.
- Production database mutation risk.
- Destructive command required without explicit approval.
- Unknown deploy target.
- Missing rollback plan for deployment.
- Relevant tests cannot be run and no alternate evidence exists.

## Approval requirements
- Commit, push, deploy, production smoke checks, production logs, and rollback execution require explicit user approval.
- Any command that may mutate production resources requires explicit user approval.

## Expected output format
1. Validation level reached.
2. Commands run.
3. Evidence summary.
4. Passed checks.
5. Failed/unknown/not-tested checks.
6. Security notes.
7. Gate decision: PASS / FAIL / UNKNOWN.
8. Required next action.
