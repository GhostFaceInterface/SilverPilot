import importlib.util
from pathlib import Path


def _load_revision_module():
    revision_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "e0f7a634cb21_add_saas_tables.py"
    spec = importlib.util.spec_from_file_location("add_saas_tables", revision_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_saas_migration_defines_upgrade_and_downgrade(monkeypatch):
    revision = _load_revision_module()
    calls = []

    class FakeOp:
        @staticmethod
        def f(name):
            return name

        @staticmethod
        def create_table(name, *args, **kwargs):
            calls.append(("create_table", name))

        @staticmethod
        def create_index(name, table_name, columns, unique=False):
            calls.append(("create_index", name, table_name))

        @staticmethod
        def drop_table(name, *args, **kwargs):
            calls.append(("drop_table", name))

        @staticmethod
        def drop_index(name, table_name, *args, **kwargs):
            calls.append(("drop_index", name, table_name))

    monkeypatch.setattr(revision, "op", FakeOp)

    revision.upgrade()
    revision.downgrade()

    assert calls == [
        ("create_table", "providers"),
        ("create_index", "ix_providers_name", "providers"),
        ("create_table", "tenant_portfolios"),
        ("create_index", "ix_tenant_portfolios_tenant_id", "tenant_portfolios"),
        ("create_index", "ix_tenant_portfolios_portfolio_id", "tenant_portfolios"),
        ("create_index", "ix_tenant_portfolios_provider_id", "tenant_portfolios"),
        ("create_table", "strategy_parameters"),
        ("create_index", "ix_strategy_parameters_tenant_id", "strategy_parameters"),
        ("create_index", "ix_strategy_parameters_strategy_name", "strategy_parameters"),
        ("create_index", "ix_strategy_parameters_parameter_key", "strategy_parameters"),
        ("create_table", "asset_conversions"),
        ("create_index", "ix_asset_conversions_from_asset_id", "asset_conversions"),
        ("create_index", "ix_asset_conversions_to_asset_id", "asset_conversions"),
        ("drop_index", "ix_asset_conversions_to_asset_id", "asset_conversions"),
        ("drop_index", "ix_asset_conversions_from_asset_id", "asset_conversions"),
        ("drop_table", "asset_conversions"),
        ("drop_index", "ix_strategy_parameters_parameter_key", "strategy_parameters"),
        ("drop_index", "ix_strategy_parameters_strategy_name", "strategy_parameters"),
        ("drop_index", "ix_strategy_parameters_tenant_id", "strategy_parameters"),
        ("drop_table", "strategy_parameters"),
        ("drop_index", "ix_tenant_portfolios_provider_id", "tenant_portfolios"),
        ("drop_index", "ix_tenant_portfolios_portfolio_id", "tenant_portfolios"),
        ("drop_index", "ix_tenant_portfolios_tenant_id", "tenant_portfolios"),
        ("drop_table", "tenant_portfolios"),
        ("drop_index", "ix_providers_name", "providers"),
        ("drop_table", "providers"),
    ]
