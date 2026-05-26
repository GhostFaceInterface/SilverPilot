from decimal import Decimal

from app.core.db import SessionLocal
from app.models import Asset, Portfolio


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
            db.execute(text("DELETE FROM technical_indicators WHERE price_snapshot_id IN (SELECT id FROM price_snapshots WHERE asset_id = :aid)"), {"aid": old_asset.id})
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

        db.commit()
    finally:
        db.close()


def main() -> None:
    seed_development_data()


if __name__ == "__main__":
    main()
