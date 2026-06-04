# Deploy Gate

Use `.codex/workflows/deploy-readiness.md` and `.codex/workflows/release-gate.md`.

Required response:
1. Target environment.
2. Commit/version to deploy.
3. Docker, env, migration, model/data, and health-check readiness.
4. Rollback plan.
5. Known risks.
6. Deploy readiness: PASS / FAIL / UNKNOWN.

Do not deploy without explicit user approval.
