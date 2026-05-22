#!/usr/bin/env python3
"""
SilverPilot Database Initialization Utility
Creates the entire database schema directly from SQLAlchemy models.
Bypasses Alembic migrations to support SQLite and PostgreSQL testing environments seamlessly.
"""

import os
import sys

# Path setup to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import Base, get_engine

def init_db():
    engine = get_engine()
    print(f"Initializing database schema on: {engine.url}")
    try:
        # Import entities to ensure they are registered with Base metadata
        import app.models.entities # noqa
        
        # Create all tables defined in models
        Base.metadata.create_all(bind=engine)
        print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_db()
