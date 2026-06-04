# Post-Deploy Check

Use `.codex/workflows/post-deploy-verification.md`.

Required response:
1. Target and version checked.
2. Health endpoints checked.
3. Logs/status checked.
4. Critical flows checked.
5. Result: PASS / FAIL / UNKNOWN.
6. Rollback trigger status.

Production checks require explicit user approval.
