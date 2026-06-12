#!/usr/bin/env python3
"""
SilverPilot Model Evaluation Engine (Champion vs Challenger)
Loads a challenger model from MLflow, compares it side-by-side with the active champion model
and Buy & Hold benchmark on the offline dataset, outputs a Decision Verdict, and uploads the comparison report to MLflow.
"""

import os
import sys
import pickle
import argparse
import logging
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import mlflow
import mlflow.lightgbm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("silverpilot.ml.evaluation")

FEATURES = [
    "bank_spread_percent",
    "xag_return_15m",
    "xag_return_1h",
    "xag_return_24h",
    "usd_try_return_24h",
    "volatility_24h",
    "volatility_7d",
    "xau_xag_ratio",
    "news_sentiment_score",
    "hour_of_day",
    "day_of_week",
]
LABEL = "profitable_after_costs_3d"


def print_premium_header(title: str, width: int = 89):
    print("\033[1;36m" + "=" * width + "\033[0m")
    print(f"\033[1;36m| {title.center(width - 4)} |\033[0m")
    print("\033[1;36m" + "=" * width + "\033[0m")


def evaluate_challenger(run_id: str = None, dataset_path: str = None):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.dirname(current_dir)

    # Defaults
    if not dataset_path:
        dataset_path = os.path.join(root_path, "data", "datasets", "v1.0.0", "dataset.csv")

    champion_path = os.path.join(root_path, "data", "models", "champion_model.pkl")
    logger.info(f"Loading dataset from {dataset_path}...")
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset not found at {dataset_path}. Please run build_dataset.py first.")

    df = pd.read_csv(dataset_path)
    df = df.dropna(subset=FEATURES + [LABEL])

    # Chronological sort
    if "observed_at" in df.columns:
        df["observed_at"] = pd.to_datetime(df["observed_at"], format="ISO8601")
        df = df.sort_values("observed_at").reset_index(drop=True)

    X = df[FEATURES]
    y = df[LABEL].astype(int)

    # Setup MLflow
    mlflow.set_tracking_uri(os.path.join(root_path, "mlruns"))
    mlflow.set_experiment("SilverPilot_ML_Training")
    client = mlflow.tracking.MlflowClient()

    # Resolve Run ID if not provided
    if not run_id:
        logger.info("No Run ID provided. Fetching the latest MLflow run...")
        experiment = client.get_experiment_by_name("SilverPilot_ML_Training")
        if not experiment:
            raise ValueError("SilverPilot_ML_Training experiment does not exist yet. Please train a model first.")
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id], order_by=["attribute.start_time DESC"], max_results=1
        )
        if not runs:
            raise ValueError("No MLflow runs found to evaluate.")
        run_id = runs[0].info.run_id
        logger.info(f"Latest Run ID resolved: {run_id}")

    # 1. Load Challenger Model
    logger.info(f"Loading Challenger model from MLflow Run: {run_id}...")
    challenger_uri = f"runs:/{run_id}/model"
    challenger_model = mlflow.lightgbm.load_model(challenger_uri)

    # 2. Load Champion Model
    champion_model = None
    if os.path.exists(champion_path):
        logger.info(f"Loading active Champion model from {champion_path}...")
        try:
            with open(champion_path, "rb") as f:
                champion_model = pickle.load(f)
        except Exception as e:
            logger.warning(f"Failed to load champion model from pickle: {e}. Proceeding without champion comparisons.")
    else:
        logger.info("No active Champion model found on disk.")

    # 3. Calculate Baseline Buy & Hold
    bh_win_rate = y.mean()

    # 4. Generate Predictions & Calculate Metrics
    # Challenger metrics
    challenger_preds = challenger_model.predict(X)
    chall_acc = accuracy_score(y, challenger_preds)
    chall_prec = precision_score(y, challenger_preds, zero_division=0)
    chall_rec = recall_score(y, challenger_preds, zero_division=0)
    chall_f1 = f1_score(y, challenger_preds, zero_division=0)

    # Champion metrics
    champ_acc, champ_prec, champ_rec, champ_f1 = None, None, None, None
    if champion_model is not None:
        champion_preds = champion_model.predict(X)
        champ_acc = accuracy_score(y, champion_preds)
        champ_prec = precision_score(y, champion_preds, zero_division=0)
        champ_rec = recall_score(y, champion_preds, zero_division=0)
        champ_f1 = f1_score(y, champion_preds, zero_division=0)

    # 5. Formulate Decision Verdict
    # Logic: Challenger precision must be >= Champion precision (if champion exists), and > Buy & Hold Win Rate
    is_better_than_bh = chall_prec > bh_win_rate
    is_better_than_champ = True
    if champ_prec is not None:
        is_better_than_champ = chall_prec >= champ_prec

    approved_for_promotion = is_better_than_bh and is_better_than_champ

    if approved_for_promotion:
        verdict = "APPROVED 🚀"
        verdict_color = "\033[1;32m"
        verdict_explanation = "Challenger model outperforms both Buy & Hold and the current Champion."
    else:
        verdict = "REJECTED ⚠️"
        verdict_color = "\033[1;31m"
        reasons = []
        if not is_better_than_bh:
            reasons.append(f"Precision ({chall_prec:.3f}) is below Buy & Hold Win Rate ({bh_win_rate:.3f})")
        if not is_better_than_champ:
            reasons.append(f"Precision ({chall_prec:.3f}) is below active Champion Precision ({champ_prec:.3f})")
        verdict_explanation = "Challenger model failed quality gate: " + " and ".join(reasons)

    # Print Report to console
    print_premium_header("CHALLENGER VS CHAMPION MODEL EVALUATION REPORT")
    print(f"  Challenger Run ID : {run_id}")
    print(f"  Buy & Hold Win Rate: {bh_win_rate:.4f}\n")

    chall_prec_str = f"{chall_prec:.4f}"
    champ_prec_str = f"{champ_prec:.4f}" if champ_prec is not None else "N/A"

    # Highlight precision
    chall_prec_color = "\033[1;32m" if is_better_than_bh and is_better_than_champ else "\033[1;33m"

    print("  Metric             | Challenger model   | Champion model     | Buy & Hold Baseline ")
    print("  " + "-" * 85)
    print(
        f"  Accuracy           | {chall_acc:18.4f} | {champ_acc if champ_acc is not None else 'N/A':18} | {bh_win_rate:19.4f}"
    )
    print(
        f"  Precision (Hass.)  | {chall_prec_color}{chall_prec_str:>18}\033[0m | {champ_prec_str:18} | {bh_win_rate:19.4f}"
    )
    print(
        f"  Recall (Duyar.)    | {chall_rec:18.4f} | {champ_rec if champ_rec is not None else 'N/A':18} | {'1.0000':>19}"
    )
    print(f"  F1 Score           | {chall_f1:18.4f} | {champ_f1 if champ_f1 is not None else 'N/A':18} | -")
    print("  " + "-" * 85)
    print(f"  Decision Verdict   | {verdict_color}{verdict:<18}\033[0m | {verdict_explanation}")
    print("\033[1;36m" + "=" * 89 + "\033[0m\n")

    # 6. Log Report and Verdict back to MLflow Run as artifact
    report_markdown = f"""# Challenger Evaluation Report

## Metadata
- **Challenger Run ID:** `{run_id}`
- **Evaluation Date:** {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Dataset Source:** `{dataset_path}`
- **Dataset Rows:** {len(df)}

## Model Side-by-Side Metrics

| Metric | Challenger Model | Champion Model | Buy & Hold Baseline |
| :--- | :---: | :---: | :---: |
| **Accuracy** | {chall_acc:.4f} | {f"{champ_acc:.4f}" if champ_acc is not None else "N/A"} | {bh_win_rate:.4f} |
| **Precision** | **{chall_prec:.4f}** | {f"{champ_prec:.4f}" if champ_prec is not None else "N/A"} | {bh_win_rate:.4f} |
| **Recall** | {chall_rec:.4f} | {f"{champ_rec:.4f}" if champ_rec is not None else "N/A"} | 1.0000 |
| **F1-Score** | {chall_f1:.4f} | {f"{champ_f1:.4f}" if champ_f1 is not None else "N/A"} | - |

## Decision Verdict
**Status:** {verdict}

**Explanation:** {verdict_explanation}
"""

    with mlflow.start_run(run_id=run_id):
        # Log evaluation metrics to MLflow
        mlflow.log_metric("eval_accuracy", chall_acc)
        mlflow.log_metric("eval_precision", chall_prec)
        mlflow.log_metric("eval_recall", chall_rec)
        mlflow.log_metric("eval_f1", chall_f1)
        mlflow.log_metric("eval_bh_win_rate", bh_win_rate)

        # Log verdict tags
        mlflow.set_tag("eval_verdict", "APPROVED" if approved_for_promotion else "REJECTED")
        mlflow.set_tag("eval_explanation", verdict_explanation)

        # Log full markdown report as artifact
        mlflow.log_text(report_markdown, "evaluation_report.md")
        logger.info("Successfully uploaded evaluation report to MLflow run artifacts.")

    return approved_for_promotion


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SilverPilot Model Challenger Evaluation Engine")
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="MLflow Run ID of the challenger model to evaluate (defaults to latest run)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to the offline dataset to run evaluations over",
    )

    args = parser.parse_args()
    evaluate_challenger(run_id=args.run_id, dataset_path=args.dataset)
