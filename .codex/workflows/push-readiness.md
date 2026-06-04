# Push Readiness Workflow

## Purpose
Decide whether a branch is safe to push.

## When to use
- After a local commit is created.
- Before any `git push`.

## Agents involved
- `git_guardian`
- `ci_investigator`
- `test_verifier`
- `final_reviewer`

## Required inputs
- Current branch and upstream.
- Recent commits.
- Local verification evidence.
- Expected CI workflows.

## Read-only phase
1. Inspect `git status`, branch, upstream, and recent commits.
2. Check whether the branch is ahead/behind/diverged.
3. Inspect CI workflow expectations in `.github/workflows/`.
4. Confirm local validation is not weaker than CI expectations.

## Implementation phase
No implementation occurs in this workflow. If push blockers require code changes, return to implementation.

## Verification phase
- Run `.codex/scripts/verify-git-clean.sh`.
- Run `.codex/scripts/verify-ci-status.sh` when `gh` is available.
- Confirm aggressive validation reached the required level for the change.

## Failure handling
- Block push on dirty working tree, unclear upstream, missing local verification, unresolved CI failures, or unreviewed risky changes.

## Stop conditions
- Secrets or production credentials are present.
- Local branch divergence is not understood.
- Required CI is red and not investigated.

## Approval requirements
- Do not push without explicit user approval.
- Output push command only as a proposal until approved.

## Expected output format
1. Push readiness: PASS / FAIL / UNKNOWN.
2. Branch/upstream state.
3. Local verification evidence.
4. CI expectations/status.
5. Blockers.
6. Proposed push command requiring approval.
