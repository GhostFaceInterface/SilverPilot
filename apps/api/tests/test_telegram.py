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
from app.models import Asset, Portfolio, PriceSnapshot, AgentMemoryEvent, PaperTrade
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
    assert "Açık Pozisyon Kar/Zarar:" in karzarar_res
    assert "Gerçekleşen Kar/Zarar:" in karzarar_res
    assert "Toplam Net Kar/Zarar:" in karzarar_res
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
                chat_id=987654, text="Mock Reply Content", parse_mode="HTML"
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
            chat_id=987654, text="Mock Canli Report Content", parse_mode="HTML"
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
            chat_id=987654, photo=dummy_buffer, caption="Mock Caption Content", parse_mode="HTML"
        )


def test_escape_html_response():
    from app.agents.telegram_bot import escape_html_response

    assert escape_html_response("") == ""
    assert escape_html_response(None) == ""

    # HTML characters escaping
    assert escape_html_response("hello <world> & brand") == "hello &lt;world&gt; &amp; brand"

    # Bold conversion
    assert escape_html_response("this is **bold** text") == "this is <b>bold</b> text"

    # Italic conversion
    assert escape_html_response("this is *italic* text") == "this is <i>italic</i> text"

    # Mix
    assert (
        escape_html_response("Check **bold** and *italic* with <brackets>")
        == "Check <b>bold</b> and <i>italic</i> with &lt;brackets&gt;"
    )


def test_telegram_html_tag_balance_audit():
    from app.agents.telegram_bot import (
        get_durum_text,
        get_cuzdan_text,
        get_karzarar_text,
        get_ajanlar_text,
        handle_telegram_command,
    )
    import re

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed XAG_GRAM
    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    db.add(asset)
    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("2500.00"),
        cash_balance=Decimal("2500.00"),
        is_real_money=False,
    )
    db.add(portfolio)
    db.commit()

    # Helper to audit tags balance
    def assert_html_balanced(html_str):
        # Extract all HTML tags
        tags = re.findall(r"</?[a-zA-Z0-9]+>", html_str)
        stack = []
        for tag in tags:
            if tag.startswith("</"):
                tag_name = tag[2:-1]
                assert len(stack) > 0, f"Closing tag {tag} with no opening tag in:\n{html_str}"
                last_open = stack.pop()
                assert last_open == tag_name, f"Mismatched tags: open {last_open}, close {tag_name} in:\n{html_str}"
            else:
                tag_name = tag[1:-1]
                # If it's a self closing tag like <br/>, ignore
                if not tag.endswith("/>"):
                    stack.append(tag_name)
        assert len(stack) == 0, f"Unclosed tags: {stack} in:\n{html_str}"

    # 1. Audit /durum
    durum = get_durum_text(db)
    assert_html_balanced(durum)
    assert "Gümüş &amp; Portföy Durumu" in durum or "Gümüş & Portföy Durumu" in durum
    assert "Nakitteki Bakiye:" in durum

    # 2. Audit /cuzdan
    cuzdan = get_cuzdan_text(db)
    assert_html_balanced(cuzdan)
    assert "Cüzdan Değişim Özeti" in cuzdan
    assert "Başlangıç Bakiyesi" in cuzdan

    # 3. Audit /karzarar (empty state)
    karzarar_empty = get_karzarar_text(db)
    assert_html_balanced(karzarar_empty)
    assert "Açık Pozisyon ve Kar/Zarar Durumu" in karzarar_empty
    assert "Açık Pozisyon Kar/Zarar:" in karzarar_empty
    assert "Gerçekleşen Kar/Zarar:" in karzarar_empty
    assert "Toplam Net Kar/Zarar:" in karzarar_empty
    assert "Henüz bir paper-trade işlemi bulunmuyor." in karzarar_empty

    # 4. Audit /karzarar (with trades)
    trade = PaperTrade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        action="paper_buy",
        quantity=Decimal("10.0"),
        price=Decimal("25.0"),
        gross_amount=Decimal("250.0"),
        fees=Decimal("0.5"),
        taxes=Decimal("0.5"),
        net_amount=Decimal("251.0"),
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(trade)
    db.commit()
    karzarar_filled = get_karzarar_text(db)
    assert_html_balanced(karzarar_filled)
    assert "Açık Pozisyon Kar/Zarar:" in karzarar_filled
    assert "Gerçekleşen Kar/Zarar:" in karzarar_filled
    assert "Toplam Net Kar/Zarar:" in karzarar_filled
    assert "Son 5 Paper Trade İşlemi:" in karzarar_filled
    assert "Miktar: 10.0000" in karzarar_filled

    # 5. Audit /ajanlar (empty state)
    ajanlar_empty = get_ajanlar_text(db)
    assert_html_balanced(ajanlar_empty)
    assert (
        "Ajan Teşhis &amp; Supreme Arbiter Kararları" in ajanlar_empty
        or "Ajan Teşhis & Supreme Arbiter Kararları" in ajanlar_empty
    )

    # 6. Audit /help
    help_msg = handle_telegram_command("/help", db)
    assert_html_balanced(help_msg)

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_telegram_canli_report_html_safety_merciless():
    from app.agents.telegram_bot import run_canli_analysis_report
    from app.models import TechnicalIndicator, PriceSnapshot

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed Asset XAG_GRAM
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

    # Seed snapshot & technical indicator with adversarial LLM reason containing raw HTML & Markdown
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source="yahoo-si-f",
        buy_price=Decimal("29.50"),
        sell_price=Decimal("29.50"),
        mid_price=Decimal("29.50"),
        currency="USD",
        spread_absolute=Decimal("0.0"),
        spread_percent=Decimal("0.0"),
        observed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(snapshot)
    db.flush()

    indicator = TechnicalIndicator(
        price_snapshot_id=snapshot.id,
        bar_timestamp=datetime.datetime.now(datetime.timezone.utc),
        timeframe="1d",
        close_usd_oz=Decimal("29.50"),
        rsi_14=Decimal("25.0"),
        sma_20=Decimal("30.0"),
        sma_50=Decimal("31.0"),
    )
    db.add(indicator)
    db.flush()

    # Add mock consensus event with adversarial HTML characters
    disagreement_res = AgentMemoryEvent(
        agent_name="orchestrator",
        event_type="blended_consensus_resolution",
        key="resolution_canli_test",
        value_json={
            "resolved_stance": "BULLISH",
            "resolution_markdown": "We should **BUY** gümüş now because RSI is < 30 and price is near **bb_lower** & volatility is high.",
        },
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(disagreement_res)
    db.commit()

    import re

    # Run the canli analysis report and check it escapes tags properly
    # Using magic mocks for background API scrapers
    mock_consensus_event = MagicMock()
    mock_consensus_event.value_json = {
        "resolved_stance": "BULLISH",
        "resolution_markdown": "We should **BUY** gümüş now because RSI is < 30 and price is near **bb_lower** & volatility is high.",
    }

    with (
        patch("app.collectors.public_sources.collect_kuveyt_public_silver"),
        patch("app.collectors.public_sources.collect_global_xag_usd"),
        patch("app.agents.orchestrator.run_blended_consensus_resolution", new_callable=AsyncMock) as mock_consensus,
    ):
        mock_consensus.return_value = mock_consensus_event
        settings = MagicMock()
        settings.telegram_bot_token = "dummy"
        settings.telegram_chat_id = 987654

        import sys

        if sys.version_info >= (3, 8):
            # run_canli_analysis_report is async
            import asyncio

            report = asyncio.run(run_canli_analysis_report(db, settings))

            # Verify tag balance of report
            tags = re.findall(r"</?[a-zA-Z0-9]+>", report)
            stack = []
            for tag in tags:
                if tag.startswith("</"):
                    stack.pop()
                elif not tag.endswith("/>"):
                    stack.append(tag[1:-1])
            assert len(stack) == 0, f"Unbalanced tags in /canli report: {stack}"

            # Verify the adversarial HTML was escaped but bold tags are rendered as <b>
            assert "is &lt; 30" in report
            assert "<b>BUY</b>" in report
            assert "<b>bb_lower</b>" in report

    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_send_telegram_notification_retry():
    settings = Settings(telegram_bot_token="test_token_123", telegram_chat_id=987654)
    trade_data = {
        "action": "paper_buy",
        "price": 32.50,
        "quantity": 10.0,
        "net_amount": 325.0,
        "fees": 0.05,
        "cash_balance": 2175.0,
        "xag_balance": 10.0,
        "strategy_name": "rsi",
        "indicators": {},
        "risk_decision": {
            "decision": "allow",
            "reason_code": "RISK_CHECK_PASSED",
            "risk_level": "low",
        },
    }

    from telegram.error import RetryAfter

    mock_bot_instance = MagicMock()
    mock_bot_instance.send_message = AsyncMock()
    mock_bot_instance.send_message.side_effect = [RetryAfter(retry_after=1.0), AsyncMock()]

    with (
        patch("app.services.telegram.Bot") as MockBot,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        MockBot.return_value = mock_bot_instance

        from app.services.auto_trader import send_telegram_notification

        await send_telegram_notification(trade_data, settings)

        assert mock_bot_instance.send_message.call_count == 2
        mock_sleep.assert_called_once_with(2.0)  # e.retry_after (1.0) + 1.0


@pytest.mark.anyio
async def test_send_telegram_message_success():
    from app.services.telegram import send_telegram_message

    with patch("app.services.telegram.Bot") as MockBot:
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        MockBot.return_value = mock_bot_instance

        settings = Settings(telegram_bot_token="mock_token", telegram_chat_id=123)
        res = await send_telegram_message(
            bot_token=settings.telegram_bot_token, chat_id=str(settings.telegram_chat_id), text="Hello World"
        )
        assert res is True
        mock_bot_instance.send_message.assert_called_once_with(
            chat_id="123", text="Hello World", parse_mode="HTML", disable_notification=False
        )


@pytest.mark.anyio
async def test_send_telegram_message_retry_after():
    from app.services.telegram import send_telegram_message
    from telegram.error import RetryAfter

    with (
        patch("app.services.telegram.Bot") as MockBot,
        patch("app.services.telegram.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        # First call hits rate limit, second call succeeds
        mock_bot_instance.send_message.side_effect = [RetryAfter(retry_after=0.5), AsyncMock()]
        MockBot.return_value = mock_bot_instance

        settings = Settings(telegram_bot_token="mock_token", telegram_chat_id=123)
        res = await send_telegram_message(
            bot_token=settings.telegram_bot_token,
            chat_id=str(settings.telegram_chat_id),
            text="Hello World",
            attempts=3,
        )
        assert res is True
        assert mock_bot_instance.send_message.call_count == 2
        mock_sleep.assert_called_once_with(1.5)  # 0.5 retry_after + 1.0 delay


@pytest.mark.anyio
async def test_send_telegram_message_all_failures():
    from app.services.telegram import send_telegram_message
    from telegram.error import TelegramError

    with (
        patch("app.services.telegram.Bot") as MockBot,
        patch("app.services.telegram.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        # Always fail with general telegram API error
        mock_bot_instance.send_message.side_effect = TelegramError("API Error")
        MockBot.return_value = mock_bot_instance

        settings = Settings(telegram_bot_token="mock_token", telegram_chat_id=123)
        res = await send_telegram_message(
            bot_token=settings.telegram_bot_token,
            chat_id=str(settings.telegram_chat_id),
            text="Hello World",
            attempts=3,
            backoff=0.1,
        )
        assert res is False
        assert mock_bot_instance.send_message.call_count == 3
        # Should backoff exponentially: 0.1 * 1 = 0.1s, then 0.1 * 2 = 0.2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)
