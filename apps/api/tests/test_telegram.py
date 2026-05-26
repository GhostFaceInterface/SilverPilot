import pytest
import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import create_app
from app.core.config import get_settings, Settings
from app.models import Asset, Portfolio, PriceSnapshot, AgentMemoryEvent
from app.agents.telegram_bot import handle_telegram_command, process_telegram_update


def test_telegram_commands():
    # 1. Setup in-memory sqlite
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # 2. Seed data
    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    db.add(asset)
    db.flush()

    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("2500.00"),
        cash_balance=Decimal("2500.00"),
        is_real_money=False,
    )
    db.add(portfolio)
    db.flush()

    price_snapshot = PriceSnapshot(
        asset_id=asset.id,
        source="metals-dev",
        buy_price=Decimal("25.00"),
        sell_price=Decimal("25.00"),
        mid_price=Decimal("25.00"),
        currency="USD",
        spread_absolute=Decimal("0.00"),
        spread_percent=Decimal("0.00"),
        observed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(price_snapshot)
    db.flush()

    # Create uyuşmazlık and resolution events
    disagreement = AgentMemoryEvent(
        agent_name="orchestrator",
        event_type="agent_disagreement",
        key="disagreement_test",
        value_json={
            "stances": {"news_sentiment": "BULLISH", "market_sentiment": "BEARISH"},
            "disagreements": [{"type": "SENTIMENT_CONTRADICTION", "description": "Conflict description"}],
        },
    )
    db.add(disagreement)

    resolution = AgentMemoryEvent(
        agent_name="orchestrator",
        event_type="disagreement_resolution",
        key="resolution_test",
        value_json={
            "resolved_stance": "VETO",
            "confidence": 0.90,
            "resolution_markdown": "Test Arbiter resolution details",
        },
    )
    db.add(resolution)
    db.commit()

    # 3. Test handle_telegram_command directly

    # /durum
    durum_res = handle_telegram_command("/durum", db)
    assert "Gümüş & Portföy Durumu" in durum_res
    assert "Nakitteki Bakiye:" in durum_res
    assert "2,500.00" in durum_res

    # /cuzdan
    cuzdan_res = handle_telegram_command("/cuzdan", db)
    assert "Başlangıç Bakiyesi" in cuzdan_res
    assert "2,500.00" in cuzdan_res
    assert "Anlık Portföy Değeri:" in cuzdan_res

    # /karzarar
    karzarar_res = handle_telegram_command("/karzarar", db)
    assert "Açık Pozisyon ve Kar/Zarar Durumu" in karzarar_res
    assert "Son 5 Paper Trade İşlemi:" in karzarar_res

    # /ajanlar
    ajanlar_res = handle_telegram_command("/ajanlar", db)
    assert "Ajan Teşhis & Supreme Arbiter Kararları" in ajanlar_res
    assert "Conflict description" in ajanlar_res
    assert "Test Arbiter resolution details" in ajanlar_res

    # /help
    help_res = handle_telegram_command("/help", db)
    assert "SilverPilot Telegram Portföy & Teşhis Botu" in help_res

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_telegram_webhook_route():
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

    # Override settings to have a configured Telegram bot
    def override_get_settings():
        return Settings(telegram_bot_token="test_token_123", telegram_chat_id=987654, telegram_bot_mode="webhook")

    app.dependency_overrides[get_settings] = override_get_settings

    client = TestClient(app)

    with patch("app.api.routes.process_telegram_update"):
        payload = {
            "update_id": 100,
            "message": {
                "message_id": 1,
                "from": {"id": 987654, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 987654, "type": "private"},
                "date": 1441645532,
                "text": "/durum",
            },
        }
        response = client.post("/agent/telegram/webhook", json=payload)
        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}


@pytest.mark.anyio
async def test_process_telegram_update_filtering():
    settings = Settings(telegram_bot_token="test_token_123", telegram_chat_id=987654, telegram_bot_mode="webhook")

    # 1. Test wrong chat ID (should be ignored and NOT send a message)
    wrong_update = {"message": {"chat": {"id": 11111}, "text": "/durum"}}

    with patch("app.agents.telegram_bot.Bot") as MockBot:
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance

        await process_telegram_update(wrong_update, settings=settings)
        mock_bot_instance.send_message.assert_not_called()

    # 2. Test correct chat ID (should process and send a reply)
    correct_update = {"message": {"chat": {"id": 987654}, "text": "/durum"}}

    with (
        patch("app.agents.telegram_bot.Bot") as MockBot,
        patch("app.agents.telegram_bot.SessionLocal") as MockSessionLocal,
    ):
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance

        # Mock database session inside process_telegram_update
        mock_db = MagicMock()
        MockSessionLocal.return_value.__enter__.return_value = mock_db

        # Mock handle_telegram_command return value
        with patch("app.agents.telegram_bot.handle_telegram_command") as mock_handle:
            mock_handle.return_value = "Mock Reply Content"

            await process_telegram_update(correct_update, settings=settings)

            mock_handle.assert_called_once_with("/durum", mock_db)
            mock_bot_instance.send_message.assert_called_once_with(
                chat_id=987654, text="Mock Reply Content", parse_mode="Markdown"
            )


@pytest.mark.anyio
async def test_process_telegram_update_on_demand():
    settings = Settings(telegram_bot_token="test_token_123", telegram_chat_id=987654, telegram_bot_mode="webhook")

    # 1. Test /canli
    canli_update = {"message": {"chat": {"id": 987654}, "text": "/canli"}}

    with (
        patch("app.agents.telegram_bot.Bot") as MockBot,
        patch("app.agents.telegram_bot.SessionLocal") as MockSessionLocal,
        patch("app.agents.telegram_bot.run_canli_analysis_report") as mock_canli_report,
    ):
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance
        
        mock_db = MagicMock()
        MockSessionLocal.return_value.__enter__.return_value = mock_db
        
        mock_canli_report.return_value = "Mock Canli Report Content"

        await process_telegram_update(canli_update, settings=settings)

        # Should send wait message and then the final report
        assert mock_bot_instance.send_message.call_count == 2
        mock_canli_report.assert_called_once_with(mock_db, settings)
        
        mock_bot_instance.send_message.assert_any_call(
            chat_id=987654, text="Mock Canli Report Content", parse_mode="Markdown"
        )

    # 2. Test /analiz
    analiz_update = {"message": {"chat": {"id": 987654}, "text": "/analiz"}}

    with (
        patch("app.agents.telegram_bot.Bot") as MockBot,
        patch("app.agents.telegram_bot.SessionLocal") as MockSessionLocal,
        patch("app.agents.telegram_bot.generate_daily_price_chart") as mock_chart,
        patch("app.agents.telegram_bot.generate_daily_price_caption") as mock_caption,
    ):
        mock_bot_instance = AsyncMock()
        MockBot.return_value = mock_bot_instance
        
        mock_db = MagicMock()
        MockSessionLocal.return_value.__enter__.return_value = mock_db
        
        from io import BytesIO
        dummy_buffer = BytesIO(b"dummy")
        mock_chart.return_value = dummy_buffer
        mock_caption.return_value = "Mock Caption Content"

        await process_telegram_update(analiz_update, settings=settings)

        # Should send wait message and then the photo
        mock_bot_instance.send_message.assert_called_once()
        mock_chart.assert_called_once_with(mock_db)
        mock_caption.assert_called_once_with(mock_db)
        
        mock_bot_instance.send_photo.assert_called_once_with(
            chat_id=987654,
            photo=dummy_buffer,
            caption="Mock Caption Content",
            parse_mode="Markdown"
        )
