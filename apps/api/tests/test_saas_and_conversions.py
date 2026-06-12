from decimal import Decimal
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Asset, Provider, TenantPortfolio, StrategyParameter, AssetConversion, Portfolio, PaperTrade
from app.collectors.service import CollectorError, get_conversion_rate, get_conversion_rate_with_source
from app.paper_trading.service import execute_paper_trade
from app.schemas.paper_trading import PaperTradeRequest
from app.services.seed import seed_development_data


def test_saas_models_creation():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        # 1. Create a Provider
        provider = Provider(name="test_prov", display_name="Test Provider", is_active=True, config_json={"key": "val"})
        db.add(provider)
        db.flush()

        # 2. Create a Portfolio
        portfolio = Portfolio(name="test_port", initial_cash=Decimal("100"), cash_balance=Decimal("100"))
        db.add(portfolio)
        db.flush()

        # 3. Create a TenantPortfolio
        tp = TenantPortfolio(tenant_id="tenant_1", portfolio_id=portfolio.id, provider_id=provider.id, is_active=True)
        db.add(tp)
        db.flush()

        # 4. Create a StrategyParameter
        sp = StrategyParameter(tenant_id="tenant_1", strategy_name="rsi", parameter_key="period", parameter_value="14")
        db.add(sp)
        db.flush()

        # 5. Create Asset conversion
        asset_from = Asset(symbol="FROM_AST", name="From Asset", asset_type="metal", is_active=True)
        asset_to = Asset(symbol="TO_AST", name="To Asset", asset_type="metal", is_active=True)
        db.add(asset_from)
        db.add(asset_to)
        db.flush()

        ac = AssetConversion(from_asset_id=asset_from.id, to_asset_id=asset_to.id, conversion_rate=Decimal("1.234567"))
        db.add(ac)
        db.flush()

        db.commit()

        # Fetch and verify
        p_db = db.query(Provider).filter(Provider.name == "test_prov").one()
        assert p_db.display_name == "Test Provider"
        assert p_db.config_json == {"key": "val"}

        tp_db = db.query(TenantPortfolio).filter(TenantPortfolio.tenant_id == "tenant_1").one()
        assert tp_db.portfolio_id == portfolio.id
        assert tp_db.provider_id == provider.id

        sp_db = db.query(StrategyParameter).filter(StrategyParameter.tenant_id == "tenant_1").one()
        assert sp_db.parameter_key == "period"
        assert sp_db.parameter_value == "14"

        ac_db = db.query(AssetConversion).filter(AssetConversion.from_asset_id == asset_from.id).one()
        assert ac_db.conversion_rate == Decimal("1.234567")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_get_conversion_rate_dynamic_lookup():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        # Default conversion rate lookup when not in DB
        rate_default, source_default = get_conversion_rate_with_source(db, "XAG", "XAG_GRAM")
        assert rate_default == Decimal("31.1035")
        assert source_default == "default_missing"

        # Create assets and conversion rate in DB
        asset_from = Asset(symbol="XAG", name="Silver Spot Ounce", asset_type="metal", is_active=True)
        asset_to = Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True)
        db.add(asset_from)
        db.add(asset_to)
        db.flush()

        ac = AssetConversion(from_asset_id=asset_from.id, to_asset_id=asset_to.id, conversion_rate=Decimal("32.5"))
        db.add(ac)
        db.flush()
        db.commit()

        # Dynamic conversion rate lookup from DB
        rate_db, source_db = get_conversion_rate_with_source(db, "XAG", "XAG_GRAM")
        assert rate_db == Decimal("32.5")
        assert source_db == "db"
        assert get_conversion_rate(db, "XAG", "XAG_GRAM") == Decimal("32.5")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_seed_development_data_saas_tables(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Patch SessionLocal to return our in-memory SQLite sessionmaker
    monkeypatch.setattr("app.services.seed.SessionLocal", TestingSession)

    try:
        seed_development_data()

        db = TestingSession()
        # Verify providers seeded
        providers = {p.name: p.display_name for p in db.query(Provider).all()}
        assert providers["kuveyt_turk"] == "Kuveyt Turk"
        assert providers["ziraat"] == "Ziraat Bank"

        # Verify asset conversion seeded
        xag = db.query(Asset).filter(Asset.symbol == "XAG").one()
        xag_gram = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one()
        ac = (
            db.query(AssetConversion)
            .filter(AssetConversion.from_asset_id == xag.id, AssetConversion.to_asset_id == xag_gram.id)
            .one()
        )
        assert ac.conversion_rate == Decimal("31.1035")

        # Run seed again to verify it is idempotent and doesn't duplicate
        seed_development_data()
        assert db.query(Provider).count() == 2
        assert db.query(AssetConversion).count() == 1
        assert db.query(TenantPortfolio).count() == 1

        db.close()

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_get_conversion_rate_db_error_fallback():
    from unittest.mock import MagicMock

    db_mock = MagicMock()
    db_mock.execute.side_effect = Exception("DB Connection Timeout")
    rate, source = get_conversion_rate_with_source(db_mock, "XAG", "XAG_GRAM")
    assert rate == Decimal("31.1035")
    assert source == "default_db_error"


def test_get_conversion_rate_returns_null_fallback():
    from unittest.mock import MagicMock

    db_mock = MagicMock()
    db_mock.execute.return_value.scalar_one_or_none.return_value = None
    rate, source = get_conversion_rate_with_source(db_mock, "XAG", "XAG_GRAM")
    assert rate == Decimal("31.1035")
    assert source == "default_missing"


def test_conversion_non_positive_db_rate_fails_closed():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        asset_from = Asset(symbol="XAG", name="Silver Spot Ounce", asset_type="metal", is_active=True)
        asset_to = Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True)
        db.add_all([asset_from, asset_to])
        db.flush()
        db.add(
            AssetConversion(
                from_asset_id=asset_from.id,
                to_asset_id=asset_to.id,
                conversion_rate=Decimal("0"),
            )
        )
        db.commit()

        with pytest.raises(CollectorError, match="non-positive conversion rate"):
            get_conversion_rate(db, "XAG", "XAG_GRAM")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_cost_model_uses_tenant_provider_or_kuveyt_default():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    try:
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        ziraat = Provider(name="ziraat", display_name="Ziraat Bank", is_active=True, config_json={})
        db.add_all([asset, ziraat])
        db.flush()

        default_portfolio = Portfolio(
            name="ziraat-named-but-unbound",
            base_currency="USD",
            initial_cash=Decimal("1000.000000"),
            cash_balance=Decimal("1000.000000"),
            is_real_money=False,
        )
        bound_portfolio = Portfolio(
            name="plain-bound",
            base_currency="USD",
            initial_cash=Decimal("1000.000000"),
            cash_balance=Decimal("1000.000000"),
            is_real_money=False,
        )
        db.add_all([default_portfolio, bound_portfolio])
        db.flush()
        db.add(TenantPortfolio(tenant_id="tenant-z", portfolio_id=bound_portfolio.id, provider_id=ziraat.id))
        db.commit()

        default_trade, _ = execute_paper_trade(
            db,
            PaperTradeRequest(
                portfolio_name=default_portfolio.name,
                asset_symbol="XAG_GRAM",
                action="paper_buy",
                quantity=Decimal("10.000000"),
                buy_price=Decimal("10.000000"),
                sell_price=Decimal("9.900000"),
                fees=Decimal("0"),
                taxes=Decimal("0"),
            ),
        )
        bound_trade, _ = execute_paper_trade(
            db,
            PaperTradeRequest(
                portfolio_name=bound_portfolio.name,
                asset_symbol="XAG_GRAM",
                action="paper_buy",
                quantity=Decimal("10.000000"),
                buy_price=Decimal("10.000000"),
                sell_price=Decimal("9.900000"),
                fees=Decimal("0"),
                taxes=Decimal("0"),
            ),
        )

        assert default_trade.fees == Decimal("0.000000")
        assert default_trade.taxes == Decimal("0.200000")
        assert bound_trade.fees == Decimal("0.100000")
        assert bound_trade.taxes == Decimal("0.200000")
        assert db.query(PaperTrade).count() == 2
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
