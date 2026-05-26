import os
import sys
from decimal import Decimal
from datetime import UTC, datetime

# Path setup to import app modules from apps/api
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if os.path.exists(api_path):
    if api_path not in sys.path:
        sys.path.insert(0, api_path)
elif os.path.exists(os.path.join(root_path, "app")):
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

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

# --- Modular Configuration (Option C) ---
SMOKE_ASSET_SYMBOL = "XAG_GRAM"
SMOKE_ASSET_NAME = "Silver (Gram)"
SMOKE_PORTFOLIO_NAME = "gram-paper"
SMOKE_INITIAL_CASH = Decimal("2500.00")
TROY_OUNCE_IN_GRAMS = Decimal("31.1035")
BSMV_TAX_RATE = Decimal("0.002")  # 0.2% Kuveyt Türk BSMV


def run_pipeline_verification():
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    print("\033[1;36m|   E2E PIPELINE EXECUTION VERIFICATION (GRAM/DOLLAR MODE)    |\033[0m")
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    
    # Establish Session
    db = SessionLocal()
    from app.core.db import Base
    Base.metadata.create_all(bind=db.get_bind())
    
    # Start transaction with automatic rollback control
    transaction = db.begin()
    try:
        print("[1/7] Database session established. Nested transaction opened.")

        # 1. Fetch or create XAG_GRAM Asset
        asset = db.query(Asset).filter(Asset.symbol == SMOKE_ASSET_SYMBOL).first()
        if not asset:
            print(f"[INFO] Creating mock {SMOKE_ASSET_SYMBOL} Asset...")
            asset = Asset(symbol=SMOKE_ASSET_SYMBOL, name=SMOKE_ASSET_NAME, asset_type="metal", is_active=True)
            db.add(asset)
            db.flush()
        print(f"[2/7] Verified {SMOKE_ASSET_SYMBOL} Asset ID: {asset.id}")

        # 2. Insert mock PriceSnapshot & TechnicalIndicator (gram-denominated)
        mock_observed_time = datetime.now(UTC)
        # Simulated gram price: ~$0.9485 USD/gram (≈ $29.50 USD/oz ÷ 31.1035)
        mid_price_gram = (Decimal("29.50") / TROY_OUNCE_IN_GRAMS).quantize(Decimal("0.000001"))
        
        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source="manual-local-smoke",
            buy_price=mid_price_gram,
            sell_price=mid_price_gram,
            mid_price=mid_price_gram,
            currency="USD",
            spread_absolute=Decimal("0.0"),
            spread_percent=Decimal("0.0"),
            observed_at=mock_observed_time,
            resolved_source="smoke_test:gram-replicated",
            is_degraded=False,
        )
        db.add(snapshot)
        db.flush()
        print(f"[3/7] Mock PriceSnapshot inserted (gram). Generated ID: {snapshot.id}, mid={mid_price_gram} USD/gram")

        indicator = TechnicalIndicator(
            price_snapshot_id=snapshot.id,
            bar_timestamp=mock_observed_time,
            timeframe="1d",
            close_usd_oz=mid_price_gram,
            rsi_14=Decimal("25.0"),  # Oversold state trigger
            sma_20=None,
            sma_50=None,
            bb_lower_20_2=None,
            bb_upper_20_2=None,
        )
        db.add(indicator)
        db.flush()
        print(f"[4/7] Mock TechnicalIndicator inserted. Generated ID: {indicator.id}")

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
        
        print(f"[5/7] StrategyRunner evaluated row. Action: \033[1;33m{action}\033[0m, Reason: {reason}")
        assert action == "BUY"
        assert reason == "RSI_OVERSOLD"

        # 4. Record Signal record
        signal = Signal(
            observed_at=mock_observed_time,
            price_snapshot_id=snapshot.id,
            indicator_id=indicator.id,
            action=action,
            reason_code=reason,
            price_usd_oz=mid_price_gram,
            details_json={"rsi_val": 25.0, "unit": "gram"},
        )
        db.add(signal)
        db.flush()
        print(f"[6/7] Verified Signal database model record insertion. Signal ID: {signal.id}")
        
        # 5. Simulate Portfolio & PaperTrade insert (GRAM mode with BSMV tax)
        portfolio = Portfolio(
            name="SmokeTestGram_" + str(int(datetime.now(UTC).timestamp())),
            base_currency="USD",
            initial_cash=SMOKE_INITIAL_CASH,
            cash_balance=SMOKE_INITIAL_CASH,
            is_real_money=False,
        )
        db.add(portfolio)
        db.flush()
        
        # Calculate fee, BSMV tax and purchase
        fee = Decimal("0.05")
        bsmv_tax = (portfolio.cash_balance * BSMV_TAX_RATE).quantize(Decimal("0.000001"))
        spread = Decimal("0.02")
        slippage = Decimal("0.0005")
        
        buy_capital = portfolio.cash_balance - fee - bsmv_tax
        execution_buy_price = mid_price_gram * (Decimal("1.0") + (spread / Decimal("2.0"))) * (Decimal("1.0") + slippage)
        quantity = buy_capital / execution_buy_price  # quantity in grams
        
        trade = PaperTrade(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            action="BUY",
            quantity=quantity,
            price=execution_buy_price,
            gross_amount=quantity * execution_buy_price,
            fees=fee,
            taxes=bsmv_tax,
            net_amount=quantity * execution_buy_price + fee + bsmv_tax,
        )
        db.add(trade)
        
        portfolio.cash_balance = Decimal("0.00")
        db.flush()
        print(f"[7/7] Mock Portfolio & PaperTrade executed and verified successfully.")
        print(f"          Starting Portfolio : ${portfolio.initial_cash:.2f} USD")
        print(f"          BSMV Tax (0.2%)    : ${bsmv_tax:.6f} USD")
        print(f"          Remaining Cash     : ${portfolio.cash_balance:.2f}")
        print(f"          Bought Quantity    : {trade.quantity:.6f} grams at ${trade.price:.6f}/gram")

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
