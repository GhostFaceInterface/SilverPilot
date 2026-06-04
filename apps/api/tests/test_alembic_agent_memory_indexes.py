import importlib.util
from pathlib import Path

from app.models import AgentMemoryEvent


def _load_revision_module():
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "9c7d4a6f2b10_add_agent_memory_composite_index.py"
    )
    spec = importlib.util.spec_from_file_location("add_agent_memory_composite_index", revision_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agent_memory_composite_index_revision_matches_model_and_downgrade(monkeypatch):
    model_indexes = {
        index.name: tuple(column.name for column in index.columns) for index in AgentMemoryEvent.__table__.indexes
    }
    assert model_indexes["ix_agent_memory_events_composite"] == (
        "agent_name",
        "event_type",
        "key",
        "created_at",
    )

    revision = _load_revision_module()
    calls = []

    class FakeOp:
        @staticmethod
        def f(name):
            return name

        @staticmethod
        def create_index(name, table_name, columns, unique):
            calls.append(("create_index", name, table_name, tuple(columns), unique))

        @staticmethod
        def drop_index(name, table_name):
            calls.append(("drop_index", name, table_name))

    monkeypatch.setattr(revision, "op", FakeOp)

    revision.upgrade()
    revision.downgrade()

    assert calls == [
        (
            "create_index",
            "ix_agent_memory_events_composite",
            "agent_memory_events",
            ("agent_name", "event_type", "key", "created_at"),
            False,
        ),
        ("drop_index", "ix_agent_memory_events_composite", "agent_memory_events"),
    ]
