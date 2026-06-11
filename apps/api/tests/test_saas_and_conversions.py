from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Asset, Provider, TenantPortfolio, StrategyParameter, AssetConversion, Portfolio
from app.collectors.service import get_conversion_rate
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
        rate_default = get_conversion_rate(db, "XAG", "XAG_GRAM")
        assert rate_default == Decimal("31.1035")

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
        rate_db = get_conversion_rate(db, "XAG", "XAG_GRAM")
        assert rate_db == Decimal("32.5")

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

        db.close()

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
