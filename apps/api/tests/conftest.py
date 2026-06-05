import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("PTB_TIMEDELTA", "1")

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_SQLITE_CONNECTIONS = set()


@event.listens_for(Engine, "connect")
def _track_sqlite_connection(dbapi_conn, connection_record):
    if dbapi_conn.__class__.__module__ == "sqlite3":
        _SQLITE_CONNECTIONS.add(dbapi_conn)


from app.core.db import Base


@pytest.fixture(autouse=True)
def close_tracked_sqlite_connections():
    yield
    for connection in list(_SQLITE_CONNECTIONS):
        try:
            connection.close()
        except Exception:
            pass
        finally:
            _SQLITE_CONNECTIONS.discard(connection)


@pytest.fixture()
def db_session():
    """Create an isolated in-memory SQLite session for integration tests.

    Creates all tables, yields a session, then tears everything down.
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite doesn't enforce FK constraints by default — enable them
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def anyio_backend():
    return "asyncio"
