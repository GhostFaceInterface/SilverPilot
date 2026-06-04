# Safe Commit

Prepare a commit proposal only.

Checklist:
1. Run/read `.codex/scripts/verify-git-clean.sh`.
2. Confirm staged files match the requested scope.
3. Confirm no secrets, `.env`, key files, dumps, archives, generated caches, or unintended binaries are staged.
4. Confirm validation evidence exists.
5. Propose a Conventional Commit message.

Do not run `git add` or `git commit` unless the user explicitly approves.
