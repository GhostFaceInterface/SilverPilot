from decimal import Decimal

from app.core.db import SessionLocal
from app.models import Asset, Portfolio


def seed_development_data() -> None:
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.symbol == "XAG").one_or_none()
        if asset is None:
            db.add(Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True))

        portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one_or_none()
        if portfolio is None:
            db.add(
                Portfolio(
                    name="default-paper",
                    base_currency="USD",
                    initial_cash=Decimal("600.000000"),
                    cash_balance=Decimal("600.000000"),
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
