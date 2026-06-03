# Alembic Migrations Operations Skill

Use this manual when adding new models, changing database column schemas, or managing migration runs.

## ⚠️ Safety Protocols

- **Static Inspection First:** Check the generated migration script manually before execution. Ensure target table schema mappings are correct.
- **SQLite Compatibility:** All schema changes must be validated against SQLite (used in test suites) as well as PostgreSQL.
- **Rollback Safety:** Never implement an `upgrade` step without a matching, fully functional `downgrade` step in the Alembic revision file.

---

## ⚡ Running & Generating Migrations

- **Generating Migrations:**
  Run the autogenerate tool within the API context:
  ```bash
  docker-compose exec api alembic revision --autogenerate -m "description"
  ```
- **Upgrading Schema:**
  ```bash
  docker-compose exec api alembic upgrade head
  ```
- **Downgrading Schema:**
  ```bash
  docker-compose exec api alembic downgrade -1
  ```

---

## 📅 Timezone and Datetime Hardening

- All database datetimes must be stored as timezone-aware UTC.
- Enforce timezone normalization on retrieved values to prevent comparison errors under SQLite:
  ```python
  from datetime import timezone
  
  if dt.tzinfo is None:
      dt = dt.replace(tzinfo=timezone.utc)
  ```
- Use explicit timezone offsets in PostgreSQL (`TIMESTAMP WITH TIME ZONE`).
