from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from decimal import Decimal

from app.core.db import Base, get_db
from app.main import create_app
from app.models import LLMCallTrace


def test_agent_traces_endpoints():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. Post a new trace
    trace_payload = {
        "agent_name": "TestRiskAgent",
        "model_name": "deepseek-reasoner",
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_cost_usd": "0.000493",
        "latency_ms": 1500,
        "status": "SUCCESS",
        "prompt_raw": "Analyze risk",
        "response_raw": "Risk is low",
        "error_message": None
    }
    response = client.post("/agent/trace", json=trace_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["agent_name"] == "TestRiskAgent"
    assert data["model_name"] == "deepseek-reasoner"
    assert Decimal(data["total_cost_usd"]) == Decimal("0.000493")
    assert data["created_at"] is not None

    # 2. Get list of traces
    response = client.get("/agent/traces")
    assert response.status_code == 200
    traces = response.json()
    assert len(traces) == 1
    assert traces[0]["agent_name"] == "TestRiskAgent"

    # 3. Get traces stats
    response = client.get("/agent/traces/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_calls"] == 1
    assert stats["total_cost_usd"] == 0.000493
    assert stats["avg_latency_ms"] == 1500.0
    assert len(stats["by_agent"]) == 1
    assert stats["by_agent"][0]["agent_name"] == "TestRiskAgent"
    assert stats["by_agent"][0]["calls"] == 1
    assert stats["by_agent"][0]["total_cost_usd"] == 0.000493
    assert stats["by_agent"][0]["avg_latency_ms"] == 1500.0

    assert len(stats["by_model"]) == 1
    assert stats["by_model"][0]["model_name"] == "deepseek-reasoner"


def test_agent_memory_endpoints():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. Post a new memory event
    memory_payload = {
        "agent_name": "TestNewsAgent",
        "event_type": "market_observation",
        "key": "silver_price_surge",
        "value_json": {"price": 28.5, "sentiment": "bullish", "reason": "TCMB data"}
    }
    response = client.post("/agent/memory", json=memory_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["agent_name"] == "TestNewsAgent"
    assert data["event_type"] == "market_observation"
    assert data["key"] == "silver_price_surge"
    assert data["value_json"]["price"] == 28.5
    assert data["created_at"] is not None

    # 2. Get the memory events (filtered by agent_name)
    response = client.get("/agent/memory?agent_name=TestNewsAgent")
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 1
    assert memories[0]["key"] == "silver_price_surge"

    # 3. Get with filtering by key
    response = client.get("/agent/memory?agent_name=TestNewsAgent&key=silver_price_surge")
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 1

    # 4. Get with filtering by wrong key
    response = client.get("/agent/memory?agent_name=TestNewsAgent&key=different_key")
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 0

