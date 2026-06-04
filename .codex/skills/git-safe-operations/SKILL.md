---
name: "git-safe-operations"
description: "Codex-local skill bundle for git status, diff, secret-risk, commit readiness, and push readiness."
---

# Git Safe Operations

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Review `git status`, staged files, unstaged files, and diff summary before commit proposals.
- Do not run `git add`, `git commit`, `git push`, reset, clean, rebase, or checkout without explicit user approval.
- Block commit on secret-risk content, unrelated changes, missing verification, large artifacts, or unclear scope.

## Commands
```bash
bash .codex/scripts/verify-git-clean.sh
git diff --stat
git diff --cached --stat
```

## Evidence
- Branch/upstream state.
- Staged and unstaged scope.
- Verification tied to the diff.
- Proposed commit/push command only after approval.
