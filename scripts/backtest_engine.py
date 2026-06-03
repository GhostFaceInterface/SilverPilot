import os
import sys
import argparse
from datetime import timedelta

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

from app.core.db import SessionLocal  # noqa: E402
from app.models import Asset, PriceSnapshot, TechnicalIndicator, HistoricalAgentCache  # noqa: E402
from app.services.strategy import StrategyRunner, StrategyType  # noqa: E402


def print_premium_header(title: str, width: int = 65):
    print("\033[1;36m" + "=" * width + "\033[0m")
    print(f"\033[1;36m| {title.center(width - 4)} |\033[0m")
    print("\033[1;36m" + "=" * width + "\033[0m")


def simulate_strategy(
    records,
    strategy_base_name: str,
    use_agents: bool,
    spread: float,
    tax: float,
    fee: float,
    slippage: float,
    initial_cash: float,
    db_session=None,
    verbose: bool = True,
) -> dict:
    """
    Simulates a given strategy over price records.
    Can be run as baseline (use_agents=False) or agent-assisted (use_agents=True).
    """
    # Accounting Engine State Setup
    cash = initial_cash
    position = 0.0  # Ounces of silver
    has_position = False
    buy_entry_price = 0.0
    _buy_entry_time = None

    # Stats counters
    trades_count = 0
    winning_trades = 0
    gross_profit = 0.0
    gross_loss = 0.0
    total_cost_drag = 0.0
    trade_log = []

    equity_curve = []
    timestamps = []

    # Previous SMA values for SMA Cross Strategy
    prev_sma_20 = None
    prev_sma_50 = None

    # Simulation Loop
    for idx, (snapshot, indicator) in enumerate(records):
        current_mid_price = float(snapshot.mid_price)
        observed_at = snapshot.observed_at

        # Route evaluation to the Strategy Runner
        action, reason = StrategyRunner.evaluate_all_strategies(
            close=indicator.close_usd_oz,
            rsi_14=indicator.rsi_14,
            sma_20=indicator.sma_20,
            sma_50=indicator.sma_50,
            prev_sma_20=prev_sma_20,
            prev_sma_50=prev_sma_50,
            bb_lower=indicator.bb_lower_20_2,
            bb_upper=indicator.bb_upper_20_2,
            has_open_position=has_position,
            strategy_name=strategy_base_name,
        )

        # Store current SMAs for the next iteration crossover check
        prev_sma_20 = indicator.sma_20
        prev_sma_50 = indicator.sma_50

        # Query cache if using agents
        news_sentiment = None
        risk_decision = None
        if use_agents and db_session is not None:
            lookback_limit = observed_at - timedelta(hours=24)

            # Fetch closest news sentiment prior to or equal to observed_at within 24h
            news_cache = (
                db_session.query(HistoricalAgentCache)
                .filter(HistoricalAgentCache.agent_name.in_(["hermes-agent", "news-agent"]))
                .filter(HistoricalAgentCache.event_type.in_(["hermes_sentiment", "news_sentiment"]))
                .filter(HistoricalAgentCache.timestamp <= observed_at)
                .filter(HistoricalAgentCache.timestamp >= lookback_limit)
                .order_by(HistoricalAgentCache.timestamp.desc())
                .first()
            )
            if news_cache and news_cache.value_json:
                news_sentiment = news_cache.value_json.get("sentiment") or news_cache.value_json.get("news_sentiment")

            # Fetch closest risk critique prior to or equal to observed_at within 24h
            risk_cache = (
                db_session.query(HistoricalAgentCache)
                .filter(HistoricalAgentCache.agent_name == "risk-agent")
                .filter(HistoricalAgentCache.event_type == "signal_critique")
                .filter(HistoricalAgentCache.timestamp <= observed_at)
                .filter(HistoricalAgentCache.timestamp >= lookback_limit)
                .order_by(HistoricalAgentCache.timestamp.desc())
                .first()
            )
            if risk_cache and risk_cache.value_json:
                risk_decision = risk_cache.value_json.get("decision") or risk_cache.value_json.get("risk_decision")

            if action == "BUY":
                action, veto_reason = StrategyRunner.apply_agent_filters(action, news_sentiment, risk_decision)
                if action == "HOLD":
                    if verbose:
                        print(
                            f"\033[1;35m[VETO]\033[0m {observed_at.strftime('%Y-%m-%d %H:%M')}: BUY signal vetoed. Reason: {veto_reason} | News: {news_sentiment}, Risk: {risk_decision}"
                        )
                    reason = veto_reason

        # Process actions
        if action == "BUY" and not has_position:
            # Deduct transaction fee
            buy_capital = cash - fee
            if buy_capital > 0:
                # Calculate execution retail buy price (mid_price + spread/2 + slippage)
                execution_buy_price = current_mid_price * (1.0 + (spread / 2.0)) * (1.0 + slippage)
                position = buy_capital / execution_buy_price
                cash = 0.0
                has_position = True
                buy_entry_price = execution_buy_price
                _buy_entry_time = observed_at

                # Calculate and add cost drag
                cost_drag = (execution_buy_price - current_mid_price) * position + fee
                total_cost_drag += cost_drag

                trade_log.append(
                    {
                        "index": len(trade_log) + 1,
                        "type": "BUY",
                        "time": observed_at,
                        "price": execution_buy_price,
                        "mid_price": current_mid_price,
                        "ounces": position,
                        "reason": reason,
                    }
                )
                if verbose:
                    print(
                        f"\033[1;33m[BUY]\033[0m {observed_at.strftime('%Y-%m-%d %H:%M')}: Bought {position:.4f} oz at ${execution_buy_price:.4f} (Mid: ${current_mid_price:.4f}) | Reason: {reason}"
                    )

        elif action == "SELL" and has_position:
            # Calculate execution retail sell price (mid_price - spread/2 - slippage)
            execution_sell_price = current_mid_price * (1.0 - (spread / 2.0)) * (1.0 - slippage)
            gross_proceeds = position * execution_sell_price

            # Apply Turkish metals tax (0.2% on sell transaction)
            tax_paid = gross_proceeds * tax
            net_proceeds = gross_proceeds - tax_paid - fee

            trade_pnl = net_proceeds - (position * buy_entry_price)
            cash = cash + net_proceeds
            trades_count += 1

            if trade_pnl > 0:
                winning_trades += 1
                gross_profit += trade_pnl
            else:
                gross_loss += abs(trade_pnl)

            # Calculate and add cost drag
            cost_drag = (current_mid_price - execution_sell_price) * position + tax_paid + fee
            total_cost_drag += cost_drag

            trade_log.append(
                {
                    "index": len(trade_log) + 1,
                    "type": "SELL",
                    "time": observed_at,
                    "price": execution_sell_price,
                    "mid_price": current_mid_price,
                    "ounces": position,
                    "reason": reason,
                    "pnl": trade_pnl,
                    "tax": tax_paid,
                }
            )

            if verbose:
                pnl_color = "\033[1;32m" if trade_pnl >= 0 else "\033[1;31m"
                print(
                    f"\033[1;31m[SELL]\033[0m {observed_at.strftime('%Y-%m-%d %H:%M')}: Sold {position:.4f} oz at ${execution_sell_price:.4f} (Mid: ${current_mid_price:.4f}) | Net Proceeds: ${net_proceeds:.2f} | PnL: {pnl_color}${trade_pnl:+.2f}\033[0m | Reason: {reason}"
                )

            position = 0.0
            has_position = False
            buy_entry_price = 0.0
            _buy_entry_time = None

        # Calculate and store current equity status
        current_equity = cash + (position * current_mid_price)
        equity_curve.append(current_equity)
        timestamps.append(observed_at)

    # 4. Final Liquidation / Unrealized Account Reconciliation
    final_mid_price = float(records[-1][0].mid_price)
    final_time = records[-1][0].observed_at

    if has_position:
        # Conservative liquidation at retail sell price at the final step
        execution_sell_price = final_mid_price * (1.0 - (spread / 2.0)) * (1.0 - slippage)
        gross_proceeds = position * execution_sell_price
        tax_paid = gross_proceeds * tax
        net_proceeds = gross_proceeds - tax_paid - fee

        ending_balance = cash + net_proceeds
        trade_pnl = net_proceeds - (position * buy_entry_price)
        trades_count += 1

        if trade_pnl > 0:
            winning_trades += 1
            gross_profit += trade_pnl
        else:
            gross_loss += abs(trade_pnl)

        cost_drag = (final_mid_price - execution_sell_price) * position + tax_paid + fee
        total_cost_drag += cost_drag

        trade_log.append(
            {
                "index": len(trade_log) + 1,
                "type": "LIQ_EXIT",
                "time": final_time,
                "price": execution_sell_price,
                "mid_price": final_mid_price,
                "ounces": position,
                "reason": "FINAL_STEP_LIQUIDATION",
                "pnl": trade_pnl,
                "tax": tax_paid,
            }
        )
        if verbose:
            pnl_color = "\033[1;32m" if trade_pnl >= 0 else "\033[1;31m"
            print(
                f"\033[1;35m[LIQ]\033[0m {final_time.strftime('%Y-%m-%d %H:%M')}: Auto-Liquidated remaining {position:.4f} oz at ${execution_sell_price:.4f} | PnL: {pnl_color}${trade_pnl:+.2f}\033[0m"
            )
    else:
        ending_balance = cash

    # Update final equity curve step
    if equity_curve:
        equity_curve[-1] = ending_balance

    # Calculate Metrics
    net_pnl = ending_balance - initial_cash
    pnl_percent = (net_pnl / initial_cash) * 100.0
    win_rate = (winning_trades / trades_count * 100.0) if trades_count > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 1.0)
    cost_drag_percent = (total_cost_drag / initial_cash) * 100.0

    # Calculate Max Drawdown (MDD)
    max_drawdown = 0.0
    peak = initial_cash
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0.0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        "ending_balance": ending_balance,
        "net_pnl_usd": net_pnl,
        "net_pnl_percent": pnl_percent,
        "max_drawdown": max_drawdown,
        "trades_count": trades_count,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_cost_drag": total_cost_drag,
        "cost_drag_percent": cost_drag_percent,
        "trade_log": trade_log,
        "equity_curve": equity_curve,
    }


def run_backtest(
    strategy_name: StrategyType,
    timeframe: str,
    spread: float,
    tax: float,
    fee: float,
    slippage: float,
    initial_cash: float,
):
    # Set correct database source name depending on timeframe
    if timeframe == "1d":
        source_name = "yahoo-si-f-1d"
    elif timeframe == "5m":
        source_name = "yahoo-si-f-5m"
    else:
        source_name = f"yahoo-si-f-{timeframe}"

    db = SessionLocal()
    try:
        # 1. Fetch Asset & Historical Records
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            print("\033[1;31m[ERROR] Asset XAG (Silver Spot) not found in database!\033[0m")
            return

        print(f"\033[1;34m[INFO] Loading data for {asset.name} ({asset.symbol}) from source '{source_name}'...\033[0m")

        records = (
            db.query(PriceSnapshot, TechnicalIndicator)
            .join(TechnicalIndicator, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
            .filter(PriceSnapshot.asset_id == asset.id)
            .filter(PriceSnapshot.source == source_name)
            .filter(TechnicalIndicator.timeframe == timeframe)
            .order_by(PriceSnapshot.observed_at.asc())
            .all()
        )

        total_records = len(records)
        if total_records == 0:
            if timeframe == "1d":
                print(
                    "\033[1;33m[INFO] No 1d price snapshots found. Trying fallback to 5m timeframe and 'yahoo-si-f' source...\033[0m"
                )
                timeframe = "5m"
                source_name = "yahoo-si-f"
                records = (
                    db.query(PriceSnapshot, TechnicalIndicator)
                    .join(TechnicalIndicator, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
                    .filter(PriceSnapshot.asset_id == asset.id)
                    .filter(PriceSnapshot.source == source_name)
                    .filter(TechnicalIndicator.timeframe == timeframe)
                    .order_by(PriceSnapshot.observed_at.asc())
                    .all()
                )
                total_records = len(records)

            if total_records == 0 and timeframe == "5m" and source_name == "yahoo-si-f-5m":
                print("\033[1;33m[INFO] No yahoo-si-f-5m records found. Trying fallback to 'yahoo-si-f'...\033[0m")
                source_name = "yahoo-si-f"
                records = (
                    db.query(PriceSnapshot, TechnicalIndicator)
                    .join(TechnicalIndicator, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
                    .filter(PriceSnapshot.asset_id == asset.id)
                    .filter(PriceSnapshot.source == source_name)
                    .filter(TechnicalIndicator.timeframe == timeframe)
                    .order_by(PriceSnapshot.observed_at.asc())
                    .all()
                )
                total_records = len(records)

        if total_records == 0:
            print(
                f"\033[1;31m[ERROR] No price snapshot records found for source '{source_name}' and timeframe '{timeframe}'!\033[0m"
            )
            return

        print(f"\033[1;32m[SUCCESS] Loaded {total_records} historical bars.\033[0m\n")

        # Determine strategy configuration
        run_agent_assisted = strategy_name.endswith("_with_agents")
        strategy_base = strategy_name.replace("_with_agents", "")

        print_premium_header(f"SIMULATING {strategy_name.upper()} STRATEGY", width=89)
        print(f"  Initial Balance : ${initial_cash:.2f} USD")
        print(f"  Spread Friction : {spread * 100:.2f}%")
        print(f"  Slippage Friction: {slippage * 100:.3f}%")
        print(f"  Transaction Fee : ${fee:.2f} per trade")
        print(f"  Turkish Sell Tax: {tax * 100:.2f}%\n")

        # 2. Run Simulations
        # Run baseline
        baseline_results = simulate_strategy(
            records=records,
            strategy_base_name=strategy_base,
            use_agents=False,
            spread=spread,
            tax=tax,
            fee=fee,
            slippage=slippage,
            initial_cash=initial_cash,
            db_session=None,
            verbose=(not run_agent_assisted),  # Only print logs for baseline if not running comparison
        )

        # Run agent-assisted (if requested)
        agent_results = None
        if run_agent_assisted:
            print("\033[1;35m--- AGENT-ASSISTED SIMULATION LOGS ---\033[0m")
            agent_results = simulate_strategy(
                records=records,
                strategy_base_name=strategy_base,
                use_agents=True,
                spread=spread,
                tax=tax,
                fee=fee,
                slippage=slippage,
                initial_cash=initial_cash,
                db_session=db,
                verbose=True,
            )
            print("\033[1;35m--------------------------------------\033[0m\n")

        # 3. Buy & Hold Benchmark Simulator
        first_mid_price = float(records[0][0].mid_price)
        last_mid_price = float(records[-1][0].mid_price)

        # B&H Buy
        bh_capital = initial_cash - fee
        bh_buy_price = first_mid_price * (1.0 + (spread / 2.0)) * (1.0 + slippage)
        bh_ounces = bh_capital / bh_buy_price

        # B&H Sell
        bh_sell_price = last_mid_price * (1.0 - (spread / 2.0)) * (1.0 - slippage)
        bh_gross_proceeds = bh_ounces * bh_sell_price
        bh_tax = bh_gross_proceeds * tax
        bh_net_proceeds = bh_gross_proceeds - bh_tax - fee

        bh_ending_balance = bh_net_proceeds
        bh_net_pnl = bh_ending_balance - initial_cash
        bh_pnl_percent = (bh_net_pnl / initial_cash) * 100.0

        # Drawdown of Buy & Hold over timeframe
        bh_drawdown = 0.0
        bh_peak = initial_cash
        for snapshot, _ in records:
            mid = float(snapshot.mid_price)
            # Estimate B&H value at this bar
            val = bh_ounces * mid
            if val > bh_peak:
                bh_peak = val
            dd = (bh_peak - val) / bh_peak if bh_peak > 0.0 else 0.0
            if dd > bh_drawdown:
                bh_drawdown = dd

        # 4. Print Side-by-Side Comparison Table
        print_premium_header("BACKTEST PERFORMANCE COMPARISON REPORT", width=89)

        base_net_pnl = baseline_results["net_pnl_usd"]
        agent_net_pnl = agent_results["net_pnl_usd"] if run_agent_assisted else 0.0

        base_color = "\033[1;32m" if base_net_pnl >= 0 else "\033[1;31m"
        agent_color = "\033[1;32m" if agent_net_pnl >= 0 else "\033[1;31m"
        bh_color = "\033[1;32m" if bh_net_pnl >= 0 else "\033[1;31m"

        base_alpha = baseline_results["net_pnl_percent"] - bh_pnl_percent
        agent_alpha = (agent_results["net_pnl_percent"] - bh_pnl_percent) if run_agent_assisted else 0.0

        base_alpha_color = "\033[1;32m" if base_alpha >= 0 else "\033[1;31m"
        agent_alpha_color = "\033[1;32m" if agent_alpha >= 0 else "\033[1;31m"

        agent_ending = f"${agent_results['ending_balance']:16.2f}" if run_agent_assisted else f"{'N/A':>17}"
        agent_net_pnl_val = f"{agent_color}${agent_net_pnl:+15.2f}\033[0m" if run_agent_assisted else f"{'N/A':>17}"
        agent_net_pnl_pct = (
            f"{agent_color}{agent_results['net_pnl_percent']:+16.2f}%\033[0m" if run_agent_assisted else f"{'N/A':>17}"
        )
        agent_mdd = (
            f"\033[1;31m{agent_results['max_drawdown'] * 100:16.2f}%\033[0m" if run_agent_assisted else f"{'N/A':>17}"
        )
        agent_trades = f"{agent_results['trades_count']:17}" if run_agent_assisted else f"{'N/A':>17}"

        if run_agent_assisted:
            agent_win = f"{agent_results['winning_trades']:6} / {agent_results['win_rate']:6.2f}%"
            pf_agent = (
                f"{agent_results['profit_factor']:.2f}" if agent_results["profit_factor"] != float("inf") else "N/A"
            )
            agent_drag_val = f"${agent_results['total_cost_drag']:16.2f}"
            agent_drag_pct = f"{agent_results['cost_drag_percent']:16.2f}%"
            agent_alpha_val = f"{agent_alpha_color}{agent_alpha:+16.2f}%\033[0m"
        else:
            agent_win = f"{'N/A':>17}"
            pf_agent = f"{'N/A':>17}"
            agent_drag_val = f"{'N/A':>17}"
            agent_drag_pct = f"{'N/A':>17}"
            agent_alpha_val = f"{'N/A':>17}"

        pf_base = (
            f"{baseline_results['profit_factor']:.2f}" if baseline_results["profit_factor"] != float("inf") else "N/A"
        )

        print(
            f"  Metric                      | BASELINE ({strategy_base.upper():9}) | AGENT-ASSISTED     | BUY & HOLD          "
        )
        print("  " + "-" * 85)
        print(
            f"  Ending Balance              | ${baseline_results['ending_balance']:16.2f} | {agent_ending} | ${bh_ending_balance:16.2f}"
        )
        print(
            f"  Net Profit/Loss (USD)       | {base_color}${base_net_pnl:+15.2f}\033[0m | {agent_net_pnl_val} | {bh_color}${bh_net_pnl:+15.2f}\033[0m"
        )
        print(
            f"  Net Profit/Loss (%)         | {base_color}{baseline_results['net_pnl_percent']:+16.2f}%\033[0m | {agent_net_pnl_pct} | {bh_color}{bh_pnl_percent:+16.2f}%\033[0m"
        )
        print(
            f"  Max Drawdown (MDD)          | \033[1;31m{baseline_results['max_drawdown'] * 100:16.2f}%\033[0m | {agent_mdd} | \033[1;31m{bh_drawdown * 100:16.2f}%\033[0m"
        )
        print(f"  Total Trades Executed       | {baseline_results['trades_count']:17} | {agent_trades} | {1:17}")
        print(
            f"  Winning Trades Count / %    | {baseline_results['winning_trades']:6} / {baseline_results['win_rate']:6.2f}% | {agent_win} | {'1 / 100.00%':>17}"
        )
        print(f"  Profit Factor               | {pf_base:>17} | {pf_agent:>17} | {'N/A':>17}")

        total_costs_bh = (
            (bh_buy_price - first_mid_price) * bh_ounces
            + (last_mid_price - bh_sell_price) * bh_ounces
            + bh_tax
            + (fee * 2)
        )
        bh_cost_drag_percent = (total_costs_bh / initial_cash) * 100.0
        print(
            f"  Friction Cost Drag (USD)    | ${baseline_results['total_cost_drag']:16.2f} | {agent_drag_val} | ${total_costs_bh:16.2f}"
        )
        print(
            f"  Friction Cost Drag (%)      | {baseline_results['cost_drag_percent']:16.2f}% | {agent_drag_pct} | {bh_cost_drag_percent:16.2f}%"
        )
        print("  " + "-" * 85)
        print(
            f"  \033[1;33mAlpha Created vs Benchmark  | {base_alpha_color}{base_alpha:+16.2f}%\033[0m | {agent_alpha_val} | -"
        )
        print("\033[1;36m" + "=" * 89 + "\033[0m\n")

        # Return results corresponding to the specified strategy_name for backward compatibility
        target_results = agent_results if run_agent_assisted else baseline_results

        return {
            "strategy_name": strategy_name,
            "timeframe": timeframe,
            "initial_cash": initial_cash,
            "ending_balance": target_results["ending_balance"],
            "net_pnl_usd": target_results["net_pnl_usd"],
            "net_pnl_percent": target_results["net_pnl_percent"],
            "max_drawdown": target_results["max_drawdown"],
            "trades_count": target_results["trades_count"],
            "win_rate": target_results["win_rate"],
            "profit_factor": target_results["profit_factor"],
            "total_cost_drag": target_results["total_cost_drag"],
            "cost_drag_percent": target_results["cost_drag_percent"],
            "bh_ending_balance": bh_ending_balance,
            "bh_net_pnl_usd": bh_net_pnl,
            "bh_net_pnl_percent": bh_pnl_percent,
            "bh_max_drawdown": bh_drawdown,
            "alpha_percent": (target_results["net_pnl_percent"] - bh_pnl_percent),
        }

    except Exception as exc:
        print(f"\033[1;31m[ERROR] Backtest run failed: {exc}\033[0m", file=sys.stderr)
        raise exc
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SilverPilot Premium Offline Backtesting Engine")
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["rsi", "sma_cross", "bollinger", "rsi_with_agents", "sma_cross_with_agents", "bollinger_with_agents"],
        default="rsi",
        help="Trading strategy to backtest",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1d",
        help="Timeframe to execute backtest over",
    )
    parser.add_argument(
        "--spread",
        type=float,
        default=0.02,
        help="Bank bid-ask spread ratio (e.g. 0.02 is 2 percent)",
    )
    parser.add_argument(
        "--tax",
        type=float,
        default=0.002,
        help="Turkish transaction sell tax (e.g. 0.002 is 0.2 percent)",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=0.05,
        help="Fixed transaction fee per trade in USD",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0005,
        help="Latency slippage drag (e.g. 0.0005 is 0.05 percent)",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=600.0,
        help="Starting cash amount in USD",
    )

    args = parser.parse_args()

    run_backtest(
        strategy_name=args.strategy,
        timeframe=args.timeframe,
        spread=args.spread,
        tax=args.tax,
        fee=args.fee,
        slippage=args.slippage,
        initial_cash=args.initial_cash,
    )
