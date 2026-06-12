# Architecture Audit Workflow

Use this workflow for major feature design, module boundary review, technical debt assessment, runtime agent design, financial data pipeline design, and refactor planning.

## Rules
- Do not implement.
- Do not propose rewrites for aesthetic reasons.
- Respect current project boundaries.
- Prefer incremental migration over big-bang refactor.
- Explicitly identify risk to financial simulation, ML predictions, reporting, and database integrity.

---

## Audit areas
1. FastAPI app boundaries
2. SQLAlchemy model/service separation
3. Alembic migration safety
4. Runtime financial agents under `apps/api/app/agents/`
5. API ↔ dashboard contract
6. ML model lifecycle
7. Paper trading execution path
8. Risk policy enforcement
9. Docker/deployment assumptions
10. Test coverage gaps

---

## Output
- Current state
- Structural problems
- Highest-risk coupling
- Recommended target design
- Phased plan
- Files likely affected
- Tests required
- Rollback strategy
