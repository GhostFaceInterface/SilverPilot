# Post-Deploy Verification Workflow

## Purpose
Verify that a deployment is healthy after it completes.

## When to use
- Immediately after an approved deploy.
- During incident response after a suspected regression.

## Agents involved
- `post_deploy_monitor`
- `ci_investigator`
- `rollback_planner`
- `final_reviewer`

## Required inputs
- Approved target base URL or SSH/log access command.
- Deployed version or commit.
- Critical endpoints and flows.
- Rollback trigger criteria.

## Read-only phase
1. Confirm target and deployed version.
2. Check health endpoint and critical API endpoints.
3. Inspect service status and logs without printing secrets.
4. Check CI/CD status for deploy-related workflows.

## Implementation phase
No implementation occurs. If a regression is found, choose rollback or forward-fix explicitly.

## Verification phase
- Run `.codex/scripts/verify-post-deploy.sh <base-url>` when a base URL is approved.
- Check logs for startup errors, unhandled exceptions, collector failures, and trade/risk regressions.
- Confirm dashboard/API critical flows when applicable.

## Failure handling
- Classify result as PASS, FAIL, or UNKNOWN.
- If FAIL, produce rollback trigger evidence and immediate mitigation proposal.
- If UNKNOWN, list the missing evidence.

## Stop conditions
- Health endpoint fails.
- Logs show critical runtime exceptions.
- Trading/risk guardrails behave unexpectedly.
- Rollback threshold is met.

## Approval requirements
- Production log access, production smoke tests, rollback, restart, or forward-fix deployment require explicit user approval.

## Expected output format
1. Post-deploy result: PASS / FAIL / UNKNOWN.
2. Target and version.
3. Evidence collected.
4. Critical flows checked.
5. Missing evidence.
6. Rollback or follow-up recommendation.
