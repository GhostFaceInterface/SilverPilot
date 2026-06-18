import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from silverpilot.app.backtests import BacktestConfig
from silverpilot.app.db.session import SessionLocal
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.ml_experiments import MLExperimentConfig, MLExperimentRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline SilverPilot ML edge experiments.")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--base-account-id", required=True)
    parser.add_argument("--execution-instrument-id", required=True)
    parser.add_argument("--instrument-type", choices=["reference", "execution"], required=True)
    parser.add_argument("--instrument-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--quote-source", required=True)
    parser.add_argument("--start-at", required=True)
    parser.add_argument("--end-at", required=True)
    parser.add_argument("--initial-cash", default="1000")
    parser.add_argument("--decision-latency-seconds", type=int, default=60)
    parser.add_argument("--label-horizon-bars", type=int, default=4)
    parser.add_argument("--min-edge-bps", default="0")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--output-root", default="mlruns/phase14")
    parser.add_argument(
        "--model-family",
        action="append",
        dest="model_families",
        choices=["rule_only", "dummy", "logistic_regression"],
    )
    args = parser.parse_args()

    backtest_config = BacktestConfig(
        strategy_id=UUID(args.strategy_id),
        base_account_id=UUID(args.base_account_id),
        execution_instrument_id=UUID(args.execution_instrument_id),
        instrument_type=InstrumentType(args.instrument_type),
        instrument_id=UUID(args.instrument_id),
        source=args.source,
        timeframe=args.timeframe,
        quote_source=args.quote_source,
        start_at=datetime.fromisoformat(args.start_at),
        end_at=datetime.fromisoformat(args.end_at),
        initial_cash=Decimal(args.initial_cash),
        decision_latency=timedelta(seconds=args.decision_latency_seconds),
    )
    experiment_config = MLExperimentConfig(
        backtest_config=backtest_config,
        output_root=Path(args.output_root),
        label_horizon_bars=args.label_horizon_bars,
        min_edge_bps=Decimal(args.min_edge_bps),
        slippage_bps=Decimal(args.slippage_bps),
        model_families=tuple(args.model_families or ["rule_only", "dummy", "logistic_regression"]),
    )
    with SessionLocal() as session:
        runs = MLExperimentRunner(session=session).run(config=experiment_config)
        session.commit()
        for run in runs:
            print(f"{run.model_family}: {run.status} ({run.id})")


if __name__ == "__main__":
    main()
