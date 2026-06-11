from decimal import Decimal

from app.core.db import SessionLocal
from app.models import Asset, Portfolio, Provider, AssetConversion


from sqlalchemy import text


def seed_development_data() -> None:
    db = SessionLocal()
    try:
        # 1. Clean up legacy Ounce data to prevent Foreign Key constraint errors
        # Find old IDs
        old_portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one_or_none()
        old_asset = db.query(Asset).filter(Asset.symbol == "XAG").one_or_none()

        if old_portfolio:
            db.execute(text("DELETE FROM paper_trades WHERE portfolio_id = :pid"), {"pid": old_portfolio.id})
            db.execute(text("DELETE FROM portfolio_snapshots WHERE portfolio_id = :pid"), {"pid": old_portfolio.id})
            db.delete(old_portfolio)
            db.flush()

        if old_asset:
            db.execute(text("DELETE FROM paper_trades WHERE asset_id = :aid"), {"aid": old_asset.id})
            # Clean up signals referencing these indicators to prevent Foreign Key constraint errors
            db.execute(
                text(
                    "DELETE FROM signals WHERE indicator_id IN (SELECT id FROM technical_indicators WHERE price_snapshot_id IN (SELECT id FROM price_snapshots WHERE asset_id = :aid))"
                ),
                {"aid": old_asset.id},
            )
            # Also clean up signals referencing the price snapshots
            db.execute(
                text(
                    "DELETE FROM signals WHERE price_snapshot_id IN (SELECT id FROM price_snapshots WHERE asset_id = :aid)"
                ),
                {"aid": old_asset.id},
            )
            db.execute(
                text(
                    "DELETE FROM technical_indicators WHERE price_snapshot_id IN (SELECT id FROM price_snapshots WHERE asset_id = :aid)"
                ),
                {"aid": old_asset.id},
            )
            db.execute(text("DELETE FROM price_snapshots WHERE asset_id = :aid"), {"aid": old_asset.id})
            db.execute(text("DELETE FROM raw_bank_prices WHERE asset_id = :aid"), {"aid": old_asset.id})
            db.execute(text("DELETE FROM raw_global_prices WHERE asset_id = :aid"), {"aid": old_asset.id})
            db.delete(old_asset)
            db.flush()

        # 2. Seed modüler XAG_GRAM Asset
        asset = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one_or_none()
        if asset is None:
            asset = Asset(symbol="XAG_GRAM", name="Silver Gram", asset_type="metal", is_active=True)
            db.add(asset)
            db.flush()

        # Re-seed legacy XAG Asset (required because collectors fetch and save ounce price under XAG,
        # which is then dynamically converted/replicated to XAG_GRAM in service.py)
        xag_asset = db.query(Asset).filter(Asset.symbol == "XAG").one_or_none()
        if xag_asset is None:
            xag_asset = Asset(symbol="XAG", name="Silver Spot Ounce", asset_type="metal", is_active=True)
            db.add(xag_asset)
            db.flush()

        # 3. Seed 2500 USD gram-paper Portfolio
        portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one_or_none()
        if portfolio is None:
            db.add(
                Portfolio(
                    name="gram-paper",
                    base_currency="USD",
                    initial_cash=Decimal("2500.000000"),
                    cash_balance=Decimal("2500.000000"),
                    is_real_money=False,
                )
            )
            db.flush()

        # 4. Seed default providers (kuveyt_turk, ziraat)
        existing_providers = {
            p.name for p in db.query(Provider).filter(Provider.name.in_(["kuveyt_turk", "ziraat"])).all()
        }
        ("kuveyt_turk" not in existing_providers) and db.add(
            Provider(name="kuveyt_turk", display_name="Kuveyt Turk", is_active=True, config_json={})
        )
        ("ziraat" not in existing_providers) and db.add(
            Provider(name="ziraat", display_name="Ziraat Bank", is_active=True, config_json={})
        )
        db.flush()

        # 5. Seed standard XAG to XAG_GRAM conversion rate (31.1035)
        xag = db.query(Asset).filter(Asset.symbol == "XAG").one_or_none()
        xag_gram = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one_or_none()

        has_conversion = (xag is not None and xag_gram is not None) and (
            db.query(AssetConversion)
            .filter(AssetConversion.from_asset_id == xag.id, AssetConversion.to_asset_id == xag_gram.id)
            .first()
            is not None
        )

        (xag is not None and xag_gram is not None and not has_conversion) and db.add(
            AssetConversion(from_asset_id=xag.id, to_asset_id=xag_gram.id, conversion_rate=Decimal("31.1035"))
        )

        db.commit()
    finally:
        db.close()


def main() -> None:
    seed_development_data()


if __name__ == "__main__":
    main()
