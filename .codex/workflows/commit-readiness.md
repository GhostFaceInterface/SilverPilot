# Commit Readiness Workflow

## Purpose
Decide whether local changes are safe to commit.

## When to use
- After implementation and verification.
- Before any `git add` or `git commit`.

## Agents involved
- `git_guardian`
- `test_verifier`
- `security_reviewer`
- `final_reviewer`

## Required inputs
- `git status --short`
- Diff summary and staged/unstaged split.
- Verification evidence.
- Intended commit scope and message.

## Read-only phase
1. Inspect branch, status, staged files, unstaged files, and diff stats.
2. Check for secrets, `.env`, keys, database dumps, model binaries, large archives, and generated artifacts.
3. Confirm changed files match the requested task.
4. Confirm tests were run or explicitly classified as not applicable.

## Implementation phase
No implementation occurs in this workflow. If fixes are needed, return to an implementation workflow.

## Verification phase
- Run `.codex/scripts/verify-git-clean.sh`.
- Run applicable tests from `.codex/workflows/aggressive-validation.md`.
- Run secret/static checks where available.

## Failure handling
- Block commit on secret risk, unrelated changes, missing verification, unresolved failing tests, or unclear staged scope.
- Propose the smallest cleanup/fix path.

## Stop conditions
- Any secret value is present in diff or logs.
- Commit would include files outside the approved scope.
- Verification evidence is absent for runtime changes.

## Approval requirements
- Do not run `git add` or `git commit` without explicit user approval.
- Output commit commands only as proposals until approved.

## Expected output format
1. Commit readiness: PASS / FAIL / UNKNOWN.
2. Branch and staged state.
3. Files proposed for commit.
4. Verification evidence.
5. Blockers.
6. Proposed commit message.
7. Proposed commands requiring approval.
