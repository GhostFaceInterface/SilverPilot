# Database Diagnosis Workflow

Use this for schema mismatch, migration issues, missing data, wrong joins, data integrity bugs, SQLAlchemy relationship problems, Alembic failures, and PostgreSQL runtime errors.

## Safety
- Static inspection first.
- Read-only queries only.
- No migration commands without explicit approval.
- No destructive SQL.
- No production mutation unless user specifically confirms critical recovery fixes.

---

## Inspect
1. `apps/api/app/models/`
2. `apps/api/alembic/`
3. `apps/api/app/schemas/`
4. `apps/api/app/services/`
5. `scripts/init_db.py`
6. `scripts/build_dataset.py`
7. `data/local_backup.sql` only if relevant

---

## Output
- Model/table map
- Migration timeline
- Query path
- Suspected mismatch
- Safe verification query
- Fix options
- Recommended option
