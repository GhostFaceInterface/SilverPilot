import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.models import (
    Asset,
    CollectorRun,
    NotificationAudit,
    PaperTrade,
    Portfolio,
    PriceSnapshot,
    RawBankPrice,
    RawFxRate,
    RawGlobalPrice,
    RiskDecision,
    Signal,
    TechnicalIndicator,
    TradingDecisionRun,
)
from app.services.auto_trader import (
    ACTION_BUY,
    ACTION_SELL,
    StrategyResolution,
    _notification_category,
    run_auto_trading,
    should_send_trade_notification,
)
from app.services.indicator_readiness import IndicatorContext, IndicatorReadiness
from app.services.source_divergence import (
    SOURCE_DIVERGENCE_STALE_DATA,
    evaluate_source_divergence,
)


def _make_context(
    indicator: TechnicalIndicator | None,
    *,
    timeframe: str,
    usable: bool = True,
    status: str = "ready",
    reason_codes: list[str] | None = None,
    source: str = "yahoo-si-f",
) -> IndicatorContext:
    readiness = IndicatorReadiness(
        asset_symbol="XAG_GRAM",
        timeframe=timeframe,
        status=status,
        usable=usable,
        reason_codes=reason_codes or [],
        required_min_bar_count=1,
        required_fields=(),
        indicator=indicator,
        indicator_id=indicator.id if indicator is not None else None,
        market_bar_id=indicator.market_bar_id if indicator is not None else None,
        price_snapshot_id=indicator.price_snapshot_id if indicator is not None else None,
        source=source,
        bar_timestamp=indicator.bar_timestamp if indicator is not None else None,
        age_seconds=0,
        freshness_minutes=60,
        calculation_version=indicator.calculation_version if indicator is not None else None,
        quality_status="ok" if indicator is not None else None,
        input_bar_count=indicator.input_bar_count if indicator is not None else None,
        missing_required_fields=[],
        close_usd_oz=indicator.close_usd_oz if indicator is not None else None,
    )
    return IndicatorContext(readiness=readiness, previous_indicator=None)


def _seed_runtime_state():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()

    asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
    db.add(asset)
    db.flush()

    portfolio = Portfolio(
        name="gram-paper",
        base_currency="USD",
        initial_cash=Decimal("600.00"),
        cash_balance=Decimal("600.00"),
        is_real_money=False,
    )
    db.add(portfolio)
    db.flush()

    snapshots = {}
    indicators = {}
    for timeframe, price in (("1d", Decimal("31.00")), ("1h", Decimal("30.00")), ("5m", Decimal("30.20"))):
        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source="yahoo-si-f",
            buy_price=price + Decimal("0.05"),
            sell_price=price - Decimal("0.05"),
            mid_price=price,
            currency="USD",
            spread_absolute=Decimal("0.10"),
            spread_percent=Decimal("0.33"),
            observed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(snapshot)
        db.flush()
        indicator = TechnicalIndicator(
            price_snapshot_id=snapshot.id,
            bar_timestamp=datetime.datetime.now(datetime.timezone.utc),
            timeframe=timeframe,
            calculation_version="technical-indicators-v2",
            input_bar_count=100,
            quality_status="ok",
            close_usd_oz=price,
            rsi_14=Decimal("50.00"),
            macd_histogram=Decimal("0.2000"),
            bb_middle_20_2=price - Decimal("0.10"),
            bb_upper_20_2=price + Decimal("1.00"),
            bb_lower_20_2=price - Decimal("1.00"),
            sma_20=price - Decimal("0.20"),
            sma_50=price - Decimal("0.50"),
            atr_14=Decimal("0.40"),
        )
        db.add(indicator)
        db.flush()
        snapshots[timeframe] = snapshot
        indicators[timeframe] = indicator

    db.commit()
    return engine, db, asset, portfolio, snapshots, indicators


def _seed_divergent_sources(db, asset: Asset) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    xag_asset = db.execute(select(Asset).where(Asset.symbol == "XAG")).scalar_one_or_none()
    if xag_asset is None:
        xag_asset = Asset(symbol="XAG", name="Silver Ounce", asset_type="metal", is_active=True)
        db.add(xag_asset)
        db.flush()
    bank_run = CollectorRun(
        collector_name="kuveyt_public_silver",
        source="kuveyt-public-silver-page",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    global_run = CollectorRun(
        collector_name="global_xag_usd",
        source="yahoo-si-f",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    fx_run = CollectorRun(
        collector_name="tcmb_usd_try",
        source="tcmb-today-xml",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    db.add_all([bank_run, global_run, fx_run])
    db.flush()
    db.add_all(
        [
            RawBankPrice(
                collector_run_id=bank_run.id,
                asset_id=asset.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("150.000000"),
                sell_price=Decimal("148.000000"),
                currency="TRY",
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="bank-divergent",
                parser_version="kuveyt-public-finance-portal-v2",
                payload_json={},
            ),
            RawGlobalPrice(
                collector_run_id=global_run.id,
                asset_id=xag_asset.id,
                source="yahoo-si-f",
                buy_price=Decimal("31.103477"),
                sell_price=Decimal("31.103477"),
                currency="USD",
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="global-divergent",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            ),
            RawFxRate(
                collector_run_id=fx_run.id,
                source="tcmb-today-xml",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("40.000000"),
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="fx-divergent",
                parser_version="tcmb-today-xml-v1",
                payload_json={},
            ),
        ]
    )
    db.flush()


def test_source_divergence_uses_xag_ounce_not_xag_gram_replica():
    engine, db, xag_gram, _, _, _ = _seed_runtime_state()
    now = datetime.datetime.now(datetime.timezone.utc)
    xag = Asset(symbol="XAG", name="Silver Ounce", asset_type="metal", is_active=True)
    db.add(xag)
    db.flush()

    bank_run = CollectorRun(
        collector_name="kuveyt_public_silver",
        source="kuveyt-public-silver-page",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    global_run = CollectorRun(
        collector_name="global_xag_usd",
        source="yahoo-si-f",
        status="success",
        records_seen=2,
        records_inserted=2,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    fx_run = CollectorRun(
        collector_name="tcmb_usd_try",
        source="tcmb-today-xml",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=now,
        finished_at=now,
        details_json={},
    )
    db.add_all([bank_run, global_run, fx_run])
    db.flush()
    db.add_all(
        [
            RawBankPrice(
                collector_run_id=bank_run.id,
                asset_id=xag_gram.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("40.000000"),
                sell_price=Decimal("40.000000"),
                currency="TRY",
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="bank",
                parser_version="kuveyt-public-finance-portal-v2",
                payload_json={},
            ),
            RawGlobalPrice(
                collector_run_id=global_run.id,
                asset_id=xag.id,
                source="yahoo-si-f",
                buy_price=Decimal("31.1034768"),
                sell_price=Decimal("31.1034768"),
                currency="USD",
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="global-ounce",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            ),
            RawGlobalPrice(
                collector_run_id=global_run.id,
                asset_id=xag_gram.id,
                source="yahoo-si-f",
                buy_price=Decimal("1.000000"),
                sell_price=Decimal("1.000000"),
                currency="USD",
                observed_at=now + datetime.timedelta(seconds=1),
                fetched_at=now + datetime.timedelta(seconds=1),
                raw_payload_hash="global-gram-replica",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            ),
            RawFxRate(
                collector_run_id=fx_run.id,
                source="tcmb-today-xml",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("40.000000"),
                observed_at=now,
                fetched_at=now,
                raw_payload_hash="fx",
                parser_version="tcmb-today-xml-v1",
                payload_json={},
            ),
        ]
    )
    db.flush()

    result = evaluate_source_divergence(db).to_dict()

    assert result["status"] == "ok"
    assert result["blocked"] is False
    assert result["global_asset_symbol"] == "XAG"
    assert result["bank_asset_symbol"] == "XAG_GRAM"
    assert result["global_xag_usd_oz"] == Decimal("31.103477")
    assert abs(result["converted_try_gram"] - Decimal("40.000000")) < Decimal("0.000001")

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_source_divergence_stale_data_has_dedicated_reason():
    engine, db, xag_gram, _, _, _ = _seed_runtime_state()
    now = datetime.datetime.now(datetime.timezone.utc)
    stale = now - datetime.timedelta(hours=3)
    xag = Asset(symbol="XAG", name="Silver Ounce", asset_type="metal", is_active=True)
    db.add(xag)
    db.flush()
    run = CollectorRun(
        collector_name="global_xag_usd",
        source="yahoo-si-f",
        status="success",
        records_seen=1,
        records_inserted=1,
        duplicates=0,
        started_at=stale,
        finished_at=stale,
        details_json={},
    )
    db.add(run)
    db.flush()
    db.add_all(
        [
            RawBankPrice(
                collector_run_id=run.id,
                asset_id=xag_gram.id,
                source="kuveyt-public-silver-page",
                buy_price=Decimal("40.000000"),
                sell_price=Decimal("40.000000"),
                currency="TRY",
                observed_at=stale,
                fetched_at=stale,
                raw_payload_hash="bank-stale",
                parser_version="kuveyt-public-finance-portal-v2",
                payload_json={},
            ),
            RawGlobalPrice(
                collector_run_id=run.id,
                asset_id=xag.id,
                source="yahoo-si-f",
                buy_price=Decimal("31.1034768"),
                sell_price=Decimal("31.1034768"),
                currency="USD",
                observed_at=stale,
                fetched_at=stale,
                raw_payload_hash="global-stale",
                parser_version="yahoo-finance-chart-v1",
                payload_json={},
            ),
            RawFxRate(
                collector_run_id=run.id,
                source="tcmb-today-xml",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("40.000000"),
                observed_at=stale,
                fetched_at=stale,
                raw_payload_hash="fx-stale",
                parser_version="tcmb-today-xml-v1",
                payload_json={},
            ),
        ]
    )
    db.flush()

    result = evaluate_source_divergence(db)

    assert result.status == "stale_data"
    assert result.blocked is True
    assert result.reason_code == SOURCE_DIVERGENCE_STALE_DATA
    assert set(result.stale_reasons) == {"bank_price_stale", "global_xag_stale", "usd_try_stale"}

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_strategy_v2_is_default_for_auto_trading():
    settings = Settings()
    assert settings.strategy_name == "strategy_v2"
    assert settings.auto_trading_mode == "diagnostic"
    assert settings.auto_trading_asset_symbol == "XAG_GRAM"
    assert settings.auto_trading_portfolio_name == "gram-paper"
    assert settings.auto_trading_sentiment_agent_name == "hermes-agent"
    assert settings.default_provider_name == "kuveyt_turk"
    assert settings.hold_notification_cooldown_minutes == 360


@pytest.mark.anyio
async def test_auto_trading_disabled():
    engine, db, _, _, _, _ = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=False,
        strategy_name="strategy_v2",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )

    with patch("app.services.auto_trader.get_settings", return_value=settings):
        await run_auto_trading(db)

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_uses_strategy_v2_and_trade_intent():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="strategy_v2",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }
    allow_decision = RiskDecision(
        decision="allow",
        reason_code="RISK_CHECK_PASSED",
        risk_level="low",
        confidence=Decimal("1.0000"),
        details_json={},
    )
    db.add(allow_decision)
    db.flush()

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.trade_intents.evaluate_paper_trade_risk", return_value=allow_decision),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "BUY"
        assert signal.reason_code == "STRATEGY_V2_BUY_CONFIRMED"
        assert signal.details_json["strategy_name"] == "strategy_v2"
        assert signal.details_json["decision_envelope"]["mode"] == "paper"
        assert signal.details_json["decision_envelope"]["execution"]["status"] == "executed"
        assert signal.details_json["timeframe_policy"] == {"trend": "1d", "entry": "1h", "execution": "5m"}
        assert signal.details_json["stop_loss_price"] is not None
        assert signal.details_json["take_profit_price"] is not None

        trade = db.execute(select(PaperTrade).where(PaperTrade.action == "paper_buy")).scalar_one()
        assert trade.risk_decision.reason_code == "RISK_CHECK_PASSED"
        audit = db.execute(select(NotificationAudit).where(NotificationAudit.signal_id == signal.id)).scalar_one()
        assert audit.notification_action == "paper_buy"
        assert audit.sent is True
        assert portfolio.cash_balance < Decimal("0.001000")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_diagnostic_mode_does_not_execute_buy_or_sell():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="strategy_v2",
        auto_trading_mode="diagnostic",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        envelope = signal.details_json["decision_envelope"]
        assert signal.action == "BUY"
        assert envelope["mode"] == "diagnostic"
        assert envelope["candidate_action"] == "BUY"
        assert envelope["execution"] == {
            "status": "skipped",
            "skipped_reason": "diagnostic_mode",
            "trade_id": None,
        }
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()
        message_text = bot.send_message.call_args.kwargs["text"]
        assert "ALIM ADAYI (BUY)" in message_text
        assert "işlem yapılmadı" in message_text
        assert "diagnostic_mode" in message_text

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_skips_buy_when_position_already_open():
    engine, db, asset, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="strategy_v2",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    db.add(
        PaperTrade(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            action="paper_buy",
            quantity=Decimal("1.000000"),
            price=Decimal("30.000000"),
            gross_amount=Decimal("30.000000"),
            fees=Decimal("0.000000"),
            taxes=Decimal("0.000000"),
            net_amount=Decimal("30.000000"),
        )
    )
    db.flush()
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }
    resolution = StrategyResolution(
        action=ACTION_BUY,
        candidate_action=ACTION_BUY,
        reason_code="TEST_BUY_CANDIDATE",
        confidence=Decimal("0.9000"),
        details={"strategy_name": "strategy_v2", "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"}},
        stop_loss_price=Decimal("29.000000"),
        take_profit_price=Decimal("32.000000"),
        expected_exit_price=Decimal("32.000000"),
        resolved_strategy="strategy_v2",
    )

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.auto_trader._resolve_strategy_resolution", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        mock_resolve.return_value = resolution
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        run = db.execute(select(TradingDecisionRun).order_by(TradingDecisionRun.id.desc())).scalar_one()
        assert run.execution_result_json["status"] == "skipped"
        assert run.execution_result_json["skipped_reason"] == "position_already_open"
        assert db.execute(select(PaperTrade).where(PaperTrade.action == "paper_buy")).scalars().all()
        assert db.execute(select(PaperTrade).where(PaperTrade.action == "paper_sell")).scalars().all() == []
        message_text = bot.send_message.call_args.kwargs["text"]
        assert "position_already_open" in message_text
        assert "ek alım emri değildir" in message_text

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_skips_sell_when_no_open_position():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="strategy_v2",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }
    resolution = StrategyResolution(
        action=ACTION_SELL,
        candidate_action=ACTION_SELL,
        reason_code="TEST_SELL_CANDIDATE",
        confidence=Decimal("0.9000"),
        details={"strategy_name": "strategy_v2", "timeframe_policy": {"trend": "1d", "entry": "1h", "execution": "5m"}},
        resolved_strategy="strategy_v2",
    )

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.auto_trader._resolve_strategy_resolution", new_callable=AsyncMock) as mock_resolve,
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        mock_resolve.return_value = resolution
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        run = db.execute(select(TradingDecisionRun).order_by(TradingDecisionRun.id.desc())).scalar_one()
        assert run.execution_result_json["status"] == "skipped"
        assert run.execution_result_json["skipped_reason"] == "no_open_position"
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        message_text = bot.send_message.call_args.kwargs["text"]
        assert "SATIM ADAYI (SELL)" in message_text
        assert "no_open_position" in message_text
        assert "satış emri değildir" in message_text

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_blocks_on_source_divergence():
    engine, db, asset, portfolio, _, indicators = _seed_runtime_state()
    _seed_divergent_sources(db, asset)
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="strategy_v2",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "SOURCE_DIVERGENCE_BLOCK"
        assert "SOURCE_DIVERGENCE_BLOCK" in signal.details_json["readiness_block_flags"]
        assert signal.details_json["source_divergence"]["blocked"] is True
        run = db.execute(select(TradingDecisionRun).order_by(TradingDecisionRun.id.desc())).scalar_one()
        assert run.reason_code == "SOURCE_DIVERGENCE_BLOCK"
        assert run.source_health_json["source_divergence"]["status"] == "blocked"
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()
        message_text = bot.send_message.call_args.kwargs["text"]
        assert "SilverPilot Koruma Blok Raporu" in message_text
        assert "Veri Kaynağı Ayrışması" in message_text
        assert "Banka orta" in message_text
        assert "Global dönüşüm" in message_text
        assert "Ayrışma" in message_text
        assert "işlem yapılmadı" in message_text

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_invalid_strategy_blocks_without_exception_or_trade():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="missing_strategy",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        envelope = signal.details_json["decision_envelope"]
        assert signal.action == "HOLD"
        assert signal.reason_code == "BLOCKED_CONFIG_INVALID"
        assert envelope["requested_strategy"] == "missing_strategy"
        assert envelope["resolved_strategy"] is None
        assert envelope["execution"]["skipped_reason"] == "config_invalid"
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_blended_readiness_block_does_not_require_strategy_metadata():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(
        auto_trading_enabled=True,
        strategy_name="blended",
        auto_trading_mode="paper",
        telegram_bot_token="token",
        telegram_chat_id=1,
    )
    contexts = {
        "1d": _make_context(None, timeframe="1d", usable=False, status="empty", reason_codes=["INDICATOR_NOT_FOUND"]),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        envelope = signal.details_json["decision_envelope"]
        assert signal.action == "HOLD"
        assert signal.reason_code == "DAILY_TREND_MISSING"
        assert envelope["resolved_strategy"] == "blended"
        assert envelope["execution"]["skipped_reason"] == "not_actionable"
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()
        message_text = bot.send_message.call_args.kwargs["text"]
        assert "SilverPilot Koruma Blok Raporu" in message_text
        assert "Günlük trend verisi hazır değil" in message_text
        assert "1d trend" in message_text
        assert "1h giriş" in message_text
        assert "5m uygulama" in message_text
        assert "Bilgi Amaçlı Teknik Değerler" in message_text
        assert "30.0000" in message_text
        assert "30.2000" in message_text
        assert "Strateji Oylaması" not in message_text
        assert "Yüce Hakem" not in message_text
        assert "📝 <b>Gerekçe:" not in message_text

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_daily_trend_missing():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(None, timeframe="1d", usable=False, status="empty", reason_codes=["INDICATOR_NOT_FOUND"]),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "DAILY_TREND_MISSING"
        assert signal.details_json["readiness_block_flags"] == ["DAILY_TREND_MISSING"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_execution_timeframe_stale():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(indicators["1h"], timeframe="1h"),
        "5m": _make_context(
            indicators["5m"], timeframe="5m", usable=False, status="stale", reason_codes=["INDICATOR_STALE"]
        ),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "EXECUTION_TIMEFRAME_STALE"
        assert "EXECUTION_TIMEFRAME_STALE" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_entry_timeframe_stale():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d"),
        "1h": _make_context(
            indicators["1h"], timeframe="1h", usable=False, status="stale", reason_codes=["INDICATOR_STALE"]
        ),
        "5m": _make_context(indicators["5m"], timeframe="5m"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "ENTRY_TIMEFRAME_STALE"
        assert "ENTRY_TIMEFRAME_STALE" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.anyio
async def test_auto_trading_holds_when_timeframe_sources_do_not_align():
    engine, db, _, portfolio, _, indicators = _seed_runtime_state()
    settings = Settings(auto_trading_enabled=True, telegram_bot_token="token", telegram_chat_id=1)
    contexts = {
        "1d": _make_context(indicators["1d"], timeframe="1d", source="yahoo-si-f"),
        "1h": _make_context(indicators["1h"], timeframe="1h", source="gold-api-xag-usd"),
        "5m": _make_context(indicators["5m"], timeframe="5m", source="yahoo-si-f"),
    }

    with (
        patch("app.services.auto_trader.get_settings", return_value=settings),
        patch("app.services.auto_trader.get_strategy_timeframe_contexts", return_value=contexts),
        patch("app.services.telegram.Bot") as bot_cls,
    ):
        bot = AsyncMock()
        bot_cls.return_value = bot

        await run_auto_trading(db)

        signal = db.execute(select(Signal).order_by(Signal.id.desc())).scalar_one()
        assert signal.action == "HOLD"
        assert signal.reason_code == "TIMEFRAME_SOURCE_MISMATCH"
        assert "TIMEFRAME_SOURCE_MISMATCH" in signal.details_json["readiness_block_flags"]
        assert db.execute(select(PaperTrade)).scalars().all() == []
        assert portfolio.cash_balance == Decimal("600.00")
        bot.send_message.assert_called_once()

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_hold_notification_dedupes_same_reason_inside_cooldown():
    engine, db, _, _, snapshots, _ = _seed_runtime_state()
    now = datetime.datetime.now(datetime.timezone.utc)
    previous = Signal(
        observed_at=now - datetime.timedelta(minutes=30),
        price_snapshot_id=snapshots["5m"].id,
        action="HOLD",
        reason_code="DAILY_TREND_MISSING",
        price_usd_oz=Decimal("30.20"),
        details_json={
            "decision_envelope": {
                "asset_symbol": "XAG_GRAM",
                "resolved_strategy": "strategy_v2",
            }
        },
    )
    current = Signal(
        observed_at=now,
        price_snapshot_id=snapshots["5m"].id,
        action="HOLD",
        reason_code="DAILY_TREND_MISSING",
        price_usd_oz=Decimal("30.20"),
        details_json={},
    )
    db.add_all([previous, current])
    db.flush()
    db.add(
        NotificationAudit(
            signal_id=previous.id,
            asset_symbol="XAG_GRAM",
            strategy_name="strategy_v2",
            notification_action="HOLD",
            reason_code="DAILY_TREND_MISSING",
            sent=True,
            skipped_reason=None,
            cooldown_seconds=21600,
            observed_at=previous.observed_at,
            details_json={},
        )
    )
    db.flush()

    decision = should_send_trade_notification(
        db,
        signal=current,
        asset_symbol="XAG_GRAM",
        strategy_name="strategy_v2",
        notification_action="HOLD",
        cooldown_minutes=360,
    )

    assert decision == {"sent": False, "skipped_reason": "hold_cooldown", "cooldown_seconds": 21600}

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_source_divergence_notification_uses_hold_cooldown_category():
    assert (
        _notification_category({"action": "HOLD", "execution": {"status": "skipped"}}, "SOURCE_DIVERGENCE_BLOCK")
        == "block_change"
    )


def test_hold_notification_sends_when_reason_changes():
    engine, db, _, _, snapshots, _ = _seed_runtime_state()
    now = datetime.datetime.now(datetime.timezone.utc)
    previous = Signal(
        observed_at=now - datetime.timedelta(minutes=30),
        price_snapshot_id=snapshots["5m"].id,
        action="HOLD",
        reason_code="DAILY_TREND_MISSING",
        price_usd_oz=Decimal("30.20"),
        details_json={
            "decision_envelope": {
                "asset_symbol": "XAG_GRAM",
                "resolved_strategy": "strategy_v2",
            }
        },
    )
    current = Signal(
        observed_at=now,
        price_snapshot_id=snapshots["5m"].id,
        action="HOLD",
        reason_code="ENTRY_TIMEFRAME_STALE",
        price_usd_oz=Decimal("30.20"),
        details_json={},
    )
    db.add_all([previous, current])
    db.flush()
    db.add(
        NotificationAudit(
            signal_id=previous.id,
            asset_symbol="XAG_GRAM",
            strategy_name="strategy_v2",
            notification_action="HOLD",
            reason_code="DAILY_TREND_MISSING",
            sent=True,
            skipped_reason=None,
            cooldown_seconds=21600,
            observed_at=previous.observed_at,
            details_json={},
        )
    )
    db.flush()

    decision = should_send_trade_notification(
        db,
        signal=current,
        asset_symbol="XAG_GRAM",
        strategy_name="strategy_v2",
        notification_action="HOLD",
        cooldown_minutes=360,
    )

    assert decision == {"sent": True, "skipped_reason": None, "cooldown_seconds": 21600}

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_non_hold_notification_ignores_hold_cooldown():
    engine, db, _, _, snapshots, _ = _seed_runtime_state()
    now = datetime.datetime.now(datetime.timezone.utc)
    previous = Signal(
        observed_at=now - datetime.timedelta(minutes=30),
        price_snapshot_id=snapshots["5m"].id,
        action="HOLD",
        reason_code="DAILY_TREND_MISSING",
        price_usd_oz=Decimal("30.20"),
        details_json={
            "decision_envelope": {
                "asset_symbol": "XAG_GRAM",
                "resolved_strategy": "strategy_v2",
            }
        },
    )
    current = Signal(
        observed_at=now,
        price_snapshot_id=snapshots["5m"].id,
        action="BUY",
        reason_code="STRATEGY_V2_BUY_CONFIRMED",
        price_usd_oz=Decimal("30.20"),
        details_json={},
    )
    db.add_all([previous, current])
    db.flush()
    db.add(
        NotificationAudit(
            signal_id=previous.id,
            asset_symbol="XAG_GRAM",
            strategy_name="strategy_v2",
            notification_action="HOLD",
            reason_code="DAILY_TREND_MISSING",
            sent=True,
            skipped_reason=None,
            cooldown_seconds=21600,
            observed_at=previous.observed_at,
            details_json={},
        )
    )
    db.flush()

    decision = should_send_trade_notification(
        db,
        signal=current,
        asset_symbol="XAG_GRAM",
        strategy_name="strategy_v2",
        notification_action="paper_buy",
        cooldown_minutes=360,
    )

    assert decision == {"sent": True, "skipped_reason": None, "cooldown_seconds": 21600}

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
