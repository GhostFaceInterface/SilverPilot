from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from decimal import Decimal

from app.core.db import Base, get_db
from app.main import create_app
from app.core.config import get_settings, Settings


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

    # Secure token settings override
    def override_get_settings():
        return Settings(agent_api_token="test_token")

    app.dependency_overrides[get_settings] = override_get_settings

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
        "error_message": None,
    }

    # Test unauthenticated access (fails with 401)
    unauth_response = client.post("/agent/trace", json=trace_payload)
    assert unauth_response.status_code == 401

    # Test authenticated access (succeeds with 200)
    response = client.post("/agent/trace", json=trace_payload, headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["agent_name"] == "TestRiskAgent"
    assert data["model_name"] == "deepseek-reasoner"
    assert Decimal(data["total_cost_usd"]) == Decimal("0.000493")
    assert data["created_at"] is not None

    # 2. Get list of traces (fails without token, succeeds with token)
    assert client.get("/agent/traces").status_code == 401

    response = client.get("/agent/traces", headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    traces = response.json()
    assert len(traces) == 1
    assert traces[0]["agent_name"] == "TestRiskAgent"

    # 3. Get traces stats (fails without token, succeeds with token)
    assert client.get("/agent/traces/stats").status_code == 401

    response = client.get("/agent/traces/stats", headers={"X-Agent-Token": "test_token"})
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

    # Secure token settings override
    def override_get_settings():
        return Settings(agent_api_token="test_token")

    app.dependency_overrides[get_settings] = override_get_settings

    client = TestClient(app)

    # 1. Post a new memory event
    memory_payload = {
        "agent_name": "TestNewsAgent",
        "event_type": "market_observation",
        "key": "silver_price_surge",
        "value_json": {"price": 28.5, "sentiment": "bullish", "reason": "TCMB data"},
    }

    # Test unauthenticated access (fails with 401)
    unauth_response = client.post("/agent/memory", json=memory_payload)
    assert unauth_response.status_code == 401

    # Test authenticated access (succeeds with 200)
    response = client.post("/agent/memory", json=memory_payload, headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["agent_name"] == "TestNewsAgent"
    assert data["event_type"] == "market_observation"
    assert data["key"] == "silver_price_surge"
    assert data["value_json"]["price"] == 28.5
    assert data["created_at"] is not None

    # 2. Get the memory events (filtered by agent_name) (fails without token, succeeds with token)
    assert client.get("/agent/memory?agent_name=TestNewsAgent").status_code == 401

    response = client.get("/agent/memory?agent_name=TestNewsAgent", headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 1
    assert memories[0]["key"] == "silver_price_surge"

    # 3. Get with filtering by key
    response = client.get(
        "/agent/memory?agent_name=TestNewsAgent&key=silver_price_surge", headers={"X-Agent-Token": "test_token"}
    )
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 1

    # 4. Get with filtering by wrong key
    response = client.get(
        "/agent/memory?agent_name=TestNewsAgent&key=different_key", headers={"X-Agent-Token": "test_token"}
    )
    assert response.status_code == 200
    memories = response.json()
    assert len(memories) == 0


def test_agent_trigger_endpoints():
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

    # Secure token settings override
    def override_get_settings():
        return Settings(agent_api_token="test_token")

    app.dependency_overrides[get_settings] = override_get_settings

    client = TestClient(app)

    # 1. Test POST /agent/news/trigger
    assert client.post("/agent/news/trigger").status_code == 401
    from unittest.mock import patch

    with patch("app.collectors.public_sources.collect_rss_news", return_value=(None, 0)):
        response = client.post("/agent/news/trigger", headers={"X-Agent-Token": "test_token"})
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "hermes-agent"
        assert data["event_type"] == "hermes_sentiment"
        assert data["key"] == "latest_analysis"
        assert data["value_json"]["sentiment"] == "NEUTRAL"

    # 2. Test POST /agent/report/trigger
    assert client.post("/agent/report/trigger").status_code == 401
    response = client.post("/agent/report/trigger", headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["report_type"] == "daily"
    assert data["payload_json"]["portfolio_value"] == 0.0
    assert data["payload_json"]["cash_balance"] == 0.0
    assert data["payload_json"]["trades_count"] == 0
    assert "No active portfolio data or snapshots found" in data["payload_json"]["report_content"]

    # 3. Test POST /agent/risk/critique
    assert client.post("/agent/risk/critique").status_code == 401
    response = client.post("/agent/risk/critique", headers={"X-Agent-Token": "test_token"})
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "risk-agent"
    assert data["event_type"] == "signal_critique"
    assert data["key"] == "critique_signal_none"
    assert data["value_json"]["decision"] == "APPROVED"
    assert "No signals exist in the database" in data["value_json"]["critique_markdown"]

    # Test POST /agent/risk/critique with a non-existent signal_id (should return 404)
    response_404 = client.post(
        "/agent/risk/critique",
        json={"signal_id": 9999},
        headers={"X-Agent-Token": "test_token"},
    )
    assert response_404.status_code == 404
    assert "not found" in response_404.json()["detail"]

    # 4. Test POST /agent/orchestrate/run
    assert client.post("/agent/orchestrate/run").status_code == 401

    from unittest.mock import patch

    with patch("app.agents.orchestrator.run_multi_agent_analysis") as mock_orchestrator:
        mock_orchestrator.return_value = {"status": "success"}
        response = client.post("/agent/orchestrate/run", headers={"X-Agent-Token": "test_token"})
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert "triggered in background" in data["message"]
