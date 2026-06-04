# Release Gate Workflow

## Purpose
Provide the final release acceptance checklist before push, deploy, or release closeout.

## When to use
- Before deploying to staging/production.
- Before declaring an incident fixed.
- Before merging or releasing high-risk changes.

## Agents involved
- `test_verifier`
- `security_reviewer`
- `deploy_guardian`
- `rollback_planner`
- `git_guardian`
- `final_reviewer`

## Required inputs
- Change summary.
- Git diff and commit scope.
- Validation evidence by level.
- CI status.
- Deploy and rollback plans.
- Known risks.

## Read-only phase
1. Review evidence from Levels 0-6 of aggressive validation.
2. Review git diff, CI status, Docker/runtime checks, and security findings.
3. Confirm rollback plan and known risks.
4. Confirm explicit user approvals needed for push/deploy.

## Implementation phase
No implementation occurs in the gate. Any fix returns to implementation and restarts validation.

## Verification phase
- Confirm all required evidence is present and current.
- Confirm no red CI workflow is ignored.
- Confirm final reviewer and security reviewer decisions.

## Failure handling
- Block release if evidence is weak, missing, stale, unrelated, or contradicted by logs.
- Block release if rollback plan is absent.

## Stop conditions
- Missing security review.
- Missing rollback plan.
- Missing user approval for push/deploy.
- Failed or unknown required validation.

## Approval requirements
- Push, deploy, release tagging, production verification, and rollback execution require explicit user approval.

## Expected output format
1. Release gate: PASS / FAIL / UNKNOWN.
2. Validation levels satisfied.
3. Security decision.
4. Rollback readiness.
5. Known risks.
6. Required user approvals.
7. Exact next command proposal.
