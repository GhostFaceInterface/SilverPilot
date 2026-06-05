#!/usr/bin/env python3
"""
SilverPilot Model Promotion CLI
Promotes a specific challenger model from MLflow to Champion status by copying its weights to champion_model.pkl
and generating a standardized champion_metadata.json file.
"""

import os
import sys
import pickle
import argparse
import logging
import json
from datetime import datetime, UTC
import mlflow
import mlflow.lightgbm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("silverpilot.ml.promotion")


def print_premium_header(title: str, width: int = 89):
    print("\033[1;36m" + "=" * width + "\033[0m")
    print(f"\033[1;36m| {title.center(width - 4)} |\033[0m")
    print("\033[1;36m" + "=" * width + "\033[0m")


def promote_model(run_id: str):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.dirname(current_dir)

    champion_model_path = os.path.join(root_path, "data", "models", "champion_model.pkl")
    champion_metadata_path = os.path.join(root_path, "data", "models", "champion_metadata.json")

    # Setup MLflow
    mlflow.set_tracking_uri(os.path.join(root_path, "mlruns"))
    client = mlflow.tracking.MlflowClient()

    logger.info(f"Retrieving run data from MLflow for Run ID: {run_id}...")
    try:
        run = client.get_run(run_id)
    except Exception as e:
        logger.error(f"Failed to fetch run '{run_id}' from MLflow: {e}")
        sys.exit(1)

    # 1. Download/Load Model Weights from MLflow and write to champion_model.pkl
    logger.info("Loading challenger model weights from MLflow...")
    model_uri = f"runs:/{run_id}/model"
    try:
        model = mlflow.lightgbm.load_model(model_uri)
    except Exception as e:
        logger.error(f"Failed to load model from model URI '{model_uri}': {e}")
        sys.exit(1)

    logger.info(f"Writing champion model weights to {champion_model_path}...")
    os.makedirs(os.path.dirname(champion_model_path), exist_ok=True)
    try:
        with open(champion_model_path, "wb") as f:
            pickle.dump(model, f)
    except Exception as e:
        logger.error(f"Failed to write champion model file: {e}")
        sys.exit(1)

    # 2. Extract metrics, parameters, and build metadata
    run_metrics = run.data.metrics
    run_params = run.data.params

    # Calculate training date from run info (milliseconds to datetime)
    start_time_ms = run.info.start_time
    training_date_utc = datetime.fromtimestamp(start_time_ms / 1000.0, UTC).isoformat()
    promoted_at_utc = datetime.now(UTC).isoformat()

    metadata = {
        "run_id": run_id,
        "model_status": "active",
        "promoted_at": promoted_at_utc,
        "training_date": training_date_utc,
        "features": run_params.get("features", "").split(","),
        "target": run_params.get("target", "profitable_after_costs_3d"),
        "metrics": {
            "mean_accuracy": run_metrics.get("mean_accuracy"),
            "mean_precision": run_metrics.get("mean_precision"),
            "mean_recall": run_metrics.get("mean_recall"),
            "mean_bh_win_rate": run_metrics.get("mean_bh_win_rate"),
            "eval_accuracy": run_metrics.get("eval_accuracy"),
            "eval_precision": run_metrics.get("eval_precision"),
            "eval_recall": run_metrics.get("eval_recall"),
            "eval_f1": run_metrics.get("eval_f1"),
            "eval_bh_win_rate": run_metrics.get("eval_bh_win_rate"),
        },
        "hyperparameters": {
            "n_estimators": int(run_params.get("n_estimators", 60)),
            "learning_rate": float(run_params.get("learning_rate", 0.03)),
            "max_depth": int(run_params.get("max_depth", 3)),
            "num_leaves": int(run_params.get("num_leaves", 7)),
            "min_child_samples": int(run_params.get("min_child_samples", 10)),
            "subsample": float(run_params.get("subsample", 0.8)),
            "colsample_bytree": float(run_params.get("colsample_bytree", 0.8)),
        },
    }

    # 3. Write metadata JSON
    logger.info(f"Writing champion metadata file to {champion_metadata_path}...")
    try:
        with open(champion_metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write metadata JSON file: {e}")
        sys.exit(1)

    print_premium_header("MODEL PROMOTED TO CHAMPION SUCCESSFULLY 🏆")
    print(f"  Run ID            : {run_id}")
    print(f"  Promoted At (UTC) : {promoted_at_utc}")
    print(f"  Training Date     : {training_date_utc}")
    print(f"  Offline Precision : {metadata['metrics']['mean_precision']:.4f}")
    print(
        f"  Eval. Precision   : {metadata['metrics']['eval_precision']:.4f} (Buy&Hold Win Rate: {metadata['metrics']['eval_bh_win_rate']:.4f})"
    )
    print("  " + "-" * 85)
    print(f"  Champion Files    : {os.path.relpath(champion_model_path, root_path)}")
    print(f"                      {os.path.relpath(champion_metadata_path, root_path)}")
    print("  Git Staging       : manual approval required; no files were staged automatically")
    print("\033[1;36m" + "=" * 89 + "\033[0m\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SilverPilot ML Model Promotion CLI")
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="MLflow Run ID of the model to promote to Champion status",
    )

    args = parser.parse_args()
    promote_model(run_id=args.run_id)
