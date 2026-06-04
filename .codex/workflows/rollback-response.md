# Rollback Response Workflow

## Purpose
Prepare an immediate rollback or mitigation plan when deployment fails or a regression appears.

## When to use
- Failed deploy.
- Post-deploy health check failure.
- Production/staging regression.
- Critical CI/CD release failure after push.

## Agents involved
- `rollback_planner`
- `deploy_guardian`
- `post_deploy_monitor`
- `security_reviewer`
- `final_reviewer`

## Required inputs
- Failed version and previous known-good version.
- Failure evidence.
- Deployment target.
- Migration history and data/model artifact changes.

## Read-only phase
1. Confirm failure scope and user impact.
2. Identify whether rollback is safe for code, image, DB, model artifact, and config.
3. Check whether forward-fix is safer than rollback.
4. Identify exact commands as proposals only.

## Implementation phase
No rollback or fix execution occurs without explicit user approval.

## Verification phase
- Confirm rollback prerequisites.
- Confirm post-rollback health checks.
- Confirm data/migration safety.

## Failure handling
- If rollback could destroy data or worsen state, block rollback and propose mitigation.
- If previous version is unknown, classify rollback readiness as UNKNOWN.

## Stop conditions
- Irreversible migration without restore plan.
- Unknown production target.
- Missing previous known-good version.
- Secret exposure in failure logs.

## Approval requirements
- Rollback execution, service restart, image pull, database migration, or production command requires explicit user approval.

## Expected output format
1. Rollback readiness: PASS / FAIL / UNKNOWN.
2. Failure trigger.
3. Rollback versus forward-fix recommendation.
4. Proposed rollback commands requiring approval.
5. Post-rollback verification plan.
6. Data safety notes.
