# Release Readiness & Git Operations Workflow

Use this workflow to perform code audits, final quality reviews, commit staging, pushing to remote, and post-deployment validation.

## 🏁 Phase 1: Quality Gate & Code Review
- Delegate code to the `final_reviewer` agent to review the `git diff`.
- Ensure all items in the implementation plan's Definition of Done (DoD) are fully met.
- Ensure all local tests are **100% green**:
  ```bash
  pytest
  ```

---

## 💾 Phase 2: Staging & Staged Checks
1. Stage the files carefully, avoiding unrelated files:
   ```bash
   git add path/to/changed_files
   ```
2. Trigger the local git pre-commit hook checks (Ruff format/lint checks):
   ```bash
   # Pre-commit hook runs automatically on git commit.
   # Verify that commit completes successfully and Ruff modifies/checks staged files.
   ```
3. If pre-commit lint fails, resolve variables/import errors and re-stage.

---

## 🚀 Phase 3: Push & Remote Deploy
1. Commit with standard conventional commit headers:
   ```bash
   git commit -m "feat/fix/docs: brief description"
   ```
2. Push changes to origin remote main:
   ```bash
   git push origin main
   ```
3. Execute the VPS remote deployment trigger script:
   ```bash
   ./scripts/deploy.sh
   ```
   This script stages, commits, pushes, logs into `silverpilot-vps` via SSH, pulls main, runs migrations, builds containers, and executes `scripts/vps_smoke.sh`.

---

## 📈 Phase 4: Post-Deploy Monitoring
- Verify endpoint health on the VPS (e.g. `/health`).
- Monitor live API container logs for several minutes to check for connection leaks, runtime exceptions, or budget errors.
- Confirm dashboard updates and check the Observability tab for live trace tracking.
