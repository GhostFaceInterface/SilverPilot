import os
import sys
from decimal import Decimal
from datetime import UTC, datetime

# Path setup to import app modules from apps/api
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import SessionLocal
from app.models import (
    Asset,
    PriceSnapshot,
    TechnicalIndicator,
    Signal,
    Portfolio,
    PaperTrade,
)
from app.services.strategy import StrategyRunner


def run_pipeline_verification():
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    print("\033[1;36m|          E2E PIPELINE EXECUTION VERIFICATION SCRIPT         |\033[0m")
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    
    # Establish Session
    db = SessionLocal()
    
    # Start transaction with automatic rollback control
    transaction = db.begin()
    try:
        print("[1/6] Database session established. Nested transaction opened.")

        # 1. Fetch or create XAG Asset
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            print("[INFO] Creating mock XAG Asset...")
            asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
            db.add(asset)
            db.flush()
        print(f"[2/6] Verified XAG Asset ID: {asset.id}")

        # 2. Insert mock PriceSnapshot & TechnicalIndicator
        mock_observed_time = datetime.now(UTC)
        mid_price = Decimal("29.50")
        
        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source="manual-local-smoke",
            buy_price=mid_price,
            sell_price=mid_price,
            mid_price=mid_price,
            currency="USD",
            spread_absolute=Decimal("0.0"),
            spread_percent=Decimal("0.0"),
            observed_at=mock_observed_time,
            resolved_source="smoke_test",
            is_degraded=False,
        )
        db.add(snapshot)
        db.flush()
        print(f"[3/6] Mock PriceSnapshot inserted. Generated ID: {snapshot.id}")

        indicator = TechnicalIndicator(
            price_snapshot_id=snapshot.id,
            bar_timestamp=mock_observed_time,
            timeframe="1d",
            close_usd_oz=mid_price,
            rsi_14=Decimal("25.0"),  # Oversold state trigger
            sma_20=None,
            sma_50=None,
            bb_lower_20_2=None,
            bb_upper_20_2=None,
        )
        db.add(indicator)
        db.flush()
        print(f"[4/6] Mock TechnicalIndicator inserted. Generated ID: {indicator.id}")

        # 3. Strategy Runner Evaluation (Mathematical & Deterministic Pure Logic)
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=indicator.close_usd_oz,
            rsi_14=indicator.rsi_14,
            sma_20=None,
            sma_50=None,
            prev_sma_20=None,
            prev_sma_50=None,
            bb_lower=None,
            bb_upper=None,
            has_open_position=False,
            strategy_name="rsi",
        )
        
        print(f"[5/6] StrategyRunner evaluated row. Action: \033[1;33m{action}\033[0m, Reason: {reason}")
        assert action == "BUY"
        assert reason == "RSI_OVERSOLD"

        # 4. Record Signal record
        signal = Signal(
            observed_at=mock_observed_time,
            price_snapshot_id=snapshot.id,
            indicator_id=indicator.id,
            action=action,
            reason_code=reason,
            price_usd_oz=mid_price,
            details_json={"rsi_val": 25.0},
        )
        db.add(signal)
        db.flush()
        print(f"[6/6] Verified Signal database model record insertion. Signal ID: {signal.id}")
        
        # 5. Simulate Portfolio & PaperTrade insert under transaction safety
        portfolio = Portfolio(
            name="SmokeTestPortfolio_" + str(int(datetime.now(UTC).timestamp())),
            base_currency="USD",
            initial_cash=Decimal("600.00"),
            cash_balance=Decimal("600.00"),
            is_real_money=False,
        )
        db.add(portfolio)
        db.flush()
        
        # Calculate fee and purchase
        fee = Decimal("0.05")
        spread = Decimal("0.02")
        slippage = Decimal("0.0005")
        
        buy_capital = portfolio.cash_balance - fee
        execution_buy_price = mid_price * (Decimal("1.0") + (spread / Decimal("2.0"))) * (Decimal("1.0") + slippage)
        quantity = buy_capital / execution_buy_price
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            action="BUY",
            quantity=quantity,
            price=execution_buy_price,
            gross_amount=quantity * execution_buy_price,
            fees=fee,
            taxes=Decimal("0.00"),
            net_amount=quantity * execution_buy_price + fee,
        )
        db.add(trade)
        
        portfolio.cash_balance = Decimal("0.00")
        db.flush()
        print(f"[SUCCESS] Mock Portfolio & PaperTrade executed and verified successfully.")
        print(f"          Starting Portfolio: ${portfolio.initial_cash:.2f}")
        print(f"          Remaining Cash    : ${portfolio.cash_balance:.2f}")
        print(f"          Bought Quantity   : {trade.quantity:.4f} oz at ${trade.price:.4f}")

        # Explicitly rollback the entire transaction to leave zero trash in the database!
        transaction.rollback()
        print("\033[1;32m[ROLLBACK] Transaction rolled back safely. Database is clean!\033[0m")
        print("\033[1;36m" + "=" * 65 + "\033[0m\n")
        return True

    except Exception as exc:
        transaction.rollback()
        print(f"\033[1;31m[ERROR] Pipeline verification failed: {exc}\033[0m")
        print("\033[1;36m" + "=" * 65 + "\033[0m\n")
        return False


if __name__ == "__main__":
    success = run_pipeline_verification()
    sys.exit(0 if success else 1)
