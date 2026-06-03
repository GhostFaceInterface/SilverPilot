# Emergency Troubleshooting Workflow

Use this workflow for production-like bugs, failing CI, runtime exceptions, deployment failures, broken dashboard behavior, database errors, and urgent regressions.

## Non-negotiable rules
- First pass is read-only.
- Do not code before diagnosis.
- Do not touch `.agent/` unless the issue is explicitly about the Antigravity framework.
- Do not confuse `/agents` runtime financial agents with `.codex/agents`.
- Do not mutate production data.
- Do not expose secrets from `.env`, logs, or config files.

---

## Phase 1 — Intake
Collect:
- Exact symptom
- Error message / stack trace
- Reproduction steps
- Recent changes
- Affected service: API, dashboard, database, ML pipeline, paper trading, runtime agents, Docker/deployment

---

## Phase 2 — Delegation
Use:
- `scout` for code path and file mapping
- `db_investigator` for SQLAlchemy/Alembic/PostgreSQL issues
- `architect` if the issue exposes structural design problems
- `troubleshooter` only after the failure path is understood

---

## Phase 3 — Diagnosis
Return:
- Confirmed facts
- Assumptions
- Unknowns
- Likely root cause
- Affected files
- Minimal fix plan
- Verification command
- Rollback plan

---

## Phase 4 — Implementation
Only after diagnosis:
- Use `implementation_worker` or `troubleshooter`
- Apply smallest safe change
- Run targeted verification
- Summarize diff
