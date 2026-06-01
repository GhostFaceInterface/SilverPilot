import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add apps/api to path so we can import app modules
sys.path.insert(0, "apps/api")

from app.models import Portfolio, PaperTrade, PortfolioSnapshot, Asset, PriceSnapshot


def scan_db(db_path):
    print("\n==================================================")
    print(f"SCANNING DATABASE: {db_path}")
    print("==================================================")

    if not os.path.exists(db_path):
        print("File does not exist.")
        return

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)

    with Session() as db:
        try:
            print("\n--- PORTFOLIOS ---")
            portfolios = db.query(Portfolio).all()
            if not portfolios:
                print("No portfolios found.")
            for p in portfolios:
                print(f"ID: {p.id} | Name: {p.name} | Cash Balance: {p.cash_balance} | Initial Cash: {p.initial_cash}")

            print("\n--- ASSETS ---")
            assets = db.query(Asset).all()
            for a in assets:
                print(f"ID: {a.id} | Symbol: {a.symbol} | Name: {a.name}")

            print("\n--- RECENT PRICE SNAPSHOTS (last 2) ---")
            snaps = db.query(PriceSnapshot).order_by(PriceSnapshot.observed_at.desc()).limit(2).all()
            for s in snaps:
                print(
                    f"ID: {s.id} | Asset ID: {s.asset_id} | Source: {s.source} | Mid: {s.mid_price} | Observed At: {s.observed_at}"
                )

            print("\n--- PAPER TRADES (last 20) ---")
            trades = db.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(20).all()
            if not trades:
                print("No paper trades found.")
            for t in trades:
                print(
                    f"ID: {t.id} | Action: {t.action} | Qty: {t.quantity} | Price: {t.price} | Net: {t.net_amount} | Created At: {t.created_at}"
                )

            print("\n--- PORTFOLIO SNAPSHOTS (last 5) ---")
            snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.observed_at.desc()).limit(5).all()
            if not snapshots:
                print("No portfolio snapshots found.")
            for s in snapshots:
                print(
                    f"ID: {s.id} | Cash: {s.cash_balance} | Qty: {s.asset_quantity} | Value: {s.portfolio_value} | Obs: {s.observed_at}"
                )
        except Exception as e:
            print(f"Error reading database {db_path}: {e}")


def main():
    paths = [
        "test_smoke.db",
        "weekly_training.db",
        "apps/api/test_smoke.db",
        "apps/api/weekly_training.db",
    ]
    for p in paths:
        scan_db(p)

    print("\n==================================================")
    print("SCANNING POSTGRESQL ON LOCALHOST")
    print("==================================================")
    postgres_url = (
        "postgresql+psycopg://silverpilot:bTv999wbFVYP6yBErdGiIdrtRkcOv6hZSygJ6xvfM2tNM8NW7Q@localhost:5432/silverpilot"
    )
    engine = create_engine(postgres_url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        try:
            print("\n--- PORTFOLIOS ---")
            portfolios = db.query(Portfolio).all()
            for p in portfolios:
                print(f"ID: {p.id} | Name: {p.name} | Cash Balance: {p.cash_balance} | Initial Cash: {p.initial_cash}")

            print("\n--- ASSETS ---")
            assets = db.query(Asset).all()
            for a in assets:
                print(f"ID: {a.id} | Symbol: {a.symbol} | Name: {a.name}")

            print("\n--- RECENT PRICE SNAPSHOTS (last 5) ---")
            snaps = db.query(PriceSnapshot).order_by(PriceSnapshot.observed_at.desc()).limit(5).all()
            for s in snaps:
                print(
                    f"ID: {s.id} | Asset ID: {s.asset_id} | Source: {s.source} | Mid: {s.mid_price} | Observed At: {s.observed_at}"
                )

            print("\n--- PAPER TRADES (last 20) ---")
            trades = db.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(20).all()
            for t in trades:
                print(
                    f"ID: {t.id} | Action: {t.action} | Qty: {t.quantity} | Price: {t.price} | Net: {t.net_amount} | Created At: {t.created_at}"
                )

            print("\n--- PORTFOLIO SNAPSHOTS (last 5) ---")
            snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.observed_at.desc()).limit(5).all()
            for s in snapshots:
                print(
                    f"ID: {s.id} | Cash: {s.cash_balance} | Qty: {s.asset_quantity} | Value: {s.portfolio_value} | Obs: {s.observed_at}"
                )
        except Exception as e:
            print(f"Error reading PostgreSQL on localhost: {e}")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
