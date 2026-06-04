# Safe Push

Prepare a push proposal only.

Checklist:
1. Confirm branch and upstream.
2. Confirm working tree is clean after commit.
3. Confirm local validation is complete.
4. Check recent CI status if `gh` is available.
5. Identify expected CI after push.

Do not run `git push` unless the user explicitly approves.
