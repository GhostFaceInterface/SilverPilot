from decimal import Decimal

from app.core.db import SessionLocal
from app.models import Asset, Portfolio


def seed_development_data() -> None:
    db = SessionLocal()
    try:
        # --- XAG (Ounce) asset — kept for global price ingestion source ---
        xag = db.query(Asset).filter(Asset.symbol == "XAG").one_or_none()
        if xag is None:
            db.add(Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True))

        # --- XAG_GRAM asset — gram-denominated silver for trading ---
        xag_gram = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").one_or_none()
        if xag_gram is None:
            db.add(Asset(symbol="XAG_GRAM", name="Silver (Gram)", asset_type="metal", is_active=True))

        # --- Remove legacy ounce portfolio if it exists ---
        legacy_portfolio = db.query(Portfolio).filter(Portfolio.name == "default-paper").one_or_none()
        if legacy_portfolio is not None:
            db.delete(legacy_portfolio)

        # --- Gram-denominated paper trading portfolio ($2500 USD) ---
        gram_portfolio = db.query(Portfolio).filter(Portfolio.name == "gram-paper").one_or_none()
        if gram_portfolio is None:
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
