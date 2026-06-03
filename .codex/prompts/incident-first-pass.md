Use the SilverPilot Codex emergency troubleshooting workflow.
First pass must be read-only.

Problem:
[PASTE ERROR / LOG / SYMPTOM HERE]

Delegate:
- Use scout to map relevant code paths.
- Use db_investigator only if schema, migration, SQLAlchemy, or PostgreSQL evidence is needed.
- Use architect only if the issue appears structural.
- Do not implement yet.

Return:
1. Confirmed facts
2. Relevant files
3. Failure path
4. Likely root cause
5. Missing evidence
6. Minimal fix plan
7. Verification commands
8. Rollback plan
