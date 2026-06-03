#!/usr/bin/env python3
import sys
import os
import argparse
import re

# Append apps/api directory to sys.path to import internal modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../apps/api")))

try:
    from app.core.config import get_settings
    from sqlalchemy import create_engine, text
except ImportError as e:
    print(f"Error: Required imports failed. Make sure virtual environment is active. {e}", file=sys.stderr)
    sys.exit(1)


def contains_mutation(sql_query: str) -> bool:
    """Checks if the query contains database modification patterns."""
    sanitized = re.sub(r"/\*.*?\*/", "", sql_query, flags=re.DOTALL)  # remove comments
    keywords = r"\b(insert|update|delete|drop|truncate|alter|create|replace|grant|revoke)\b"
    return bool(re.search(keywords, sanitized, re.IGNORECASE))


def main():
    parser = argparse.ArgumentParser(
        description="SilverPilot Codex Read-Only DB Introspection Tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tables", action="store_true", help="List all tables and row counts.")
    parser.add_argument("--schema", type=str, metavar="TABLE", help="Describe columns and constraints of TABLE.")
    parser.add_argument("--query", type=str, metavar="SQL", help="Execute a custom SQL query.")
    parser.add_argument(
        "--confirm-mutation", action="store_true", help="Confirm authorization to execute a mutating query."
    )
    parser.add_argument("--reason", type=str, help="Reason/Justification for executing a mutating database query.")

    args = parser.parse_args()

    settings = get_settings()
    db_url = settings.database_url

    # Check if database_url needs driver adjustment
    # SQLAlchemy requires postgresql+psycopg but standard sqlite needs no change.
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    try:
        engine = create_engine(db_url)
    except Exception as e:
        print(f"Connection Error: Failed to create engine. {e}", file=sys.stderr)
        sys.exit(1)

    if args.tables:
        query = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        try:
            with engine.connect() as conn:
                result = conn.execute(query)
                tables = [row[0] for row in result]
                print(f"{'Table Name':<30} | {'Row Count':<10}")
                print("-" * 43)
                for t in tables:
                    count_res = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
                    count = count_res.scalar()
                    print(f"{t:<30} | {count:<10}")
        except Exception as e:
            # Fallback for SQLite environments
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                    tables = [row[0] for row in result]
                    print(f"{'Table Name':<30} | {'Row Count':<10}")
                    print("-" * 43)
                    for t in tables:
                        if t.startswith("sqlite_"):
                            continue
                        count_res = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
                        count = count_res.scalar()
                        print(f"{t:<30} | {count:<10}")
            except Exception as ex:
                print(f"Error querying tables: {e} / SQLite fallback error: {ex}", file=sys.stderr)
                sys.exit(1)

    elif args.schema:
        table_name = args.schema
        # Inspect columns
        try:
            from sqlalchemy import inspect

            inspector = inspect(engine)
            columns = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)

            print(f"Schema for Table: '{table_name}'")
            print("-" * 50)
            print(f"{'Column Name':<25} | {'Data Type':<15} | {'Nullable':<8}")
            print("-" * 50)
            for col in columns:
                print(f"{col['name']:<25} | {str(col['type']):<15} | {str(col['nullable']):<8}")

            if pk and pk.get("constrained_columns"):
                print(f"\nPrimary Key: {', '.join(pk['constrained_columns'])}")
            if fks:
                print("\nForeign Keys:")
                for fk in fks:
                    print(
                        f"  {', '.join(fk['referred_columns'])} -> {fk['referred_table']}.{', '.join(fk['referred_columns'])}"
                    )
        except Exception as e:
            print(f"Error inspecting table schema: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.query:
        sql = args.query.strip()
        is_mutating = contains_mutation(sql)

        if is_mutating:
            if not args.confirm_mutation or not args.reason:
                print("[CRITICAL SECURITY BLOCK]", file=sys.stderr)
                print("Error: Mutating query detected! Database changes are restricted by default.", file=sys.stderr)
                print("To execute this query, you must explicitly confirm the change by passing:", file=sys.stderr)
                print('  --confirm-mutation --reason "Your explanation here"', file=sys.stderr)
                sys.exit(2)
            else:
                print(f"[MUTATION AUTHORIZED] Reason: {args.reason}")

        try:
            with engine.begin() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    rows = result.fetchall()
                    keys = result.keys()
                    # Print results nicely
                    col_widths = [max(len(str(k)), 15) for k in keys]
                    header = " | ".join(f"{str(k):<{col_widths[i]}}" for i, k in enumerate(keys))
                    print(header)
                    print("-" * len(header))
                    for row in rows:
                        print(" | ".join(f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)))
                else:
                    print(f"Query executed successfully. Rows affected: {result.rowcount}")
        except Exception as e:
            print(f"Execution Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
