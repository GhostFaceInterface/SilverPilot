#!/usr/bin/env python3
"""
SilverPilot ML Model Training Pipeline
Trains a conservative LightGBMClassifier on the offline dataset
using Walk-Forward validation, compares to Buy & Hold, and saves the champion model with MLflow tracking.
"""

import os
import sys
import pickle
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import precision_score, recall_score, accuracy_score
import mlflow
import mlflow.lightgbm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("silverpilot.ml.training")

FEATURES = [
    "bank_spread_percent", "xag_return_15m", "xag_return_1h", "xag_return_24h",
    "usd_try_return_24h", "volatility_24h", "volatility_7d", "xau_xag_ratio",
    "news_sentiment_score", "hour_of_day", "day_of_week"
]
LABEL = "profitable_after_costs_3d"


def train_and_evaluate(dataset_path: str, model_output_path: str):
    logger.info(f"Loading offline dataset from {dataset_path}...")
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset not found at {dataset_path}. Please run build_dataset.py first.")

    df = pd.read_csv(dataset_path)
    logger.info(f"Successfully loaded dataset of shape: {df.shape}")

    # Drop any leftover NaNs in features or labels
    df = df.dropna(subset=FEATURES + [LABEL])
    logger.info(f"Dataset shape after dropping NaNs: {df.shape}")

    if len(df) < 50:
        raise ValueError("Insufficient rows for robust time-series walk-forward validation.")

    # Split into features (X) and target (y)
    X = df[FEATURES]
    y = df[LABEL].astype(int)

    # Sort index chronologically to ensure time-series integrity (very critical to prevent leakage)
    if "observed_at" in df.columns:
        df["observed_at"] = pd.to_datetime(df["observed_at"], format="ISO8601")
        df = df.sort_values("observed_at").reset_index(drop=True)

        X = df[FEATURES]
        y = df[LABEL].astype(int)

    # Setup MLflow Tracking
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.dirname(current_dir)
    mlflow.set_tracking_uri(os.path.join(root_path, "mlruns"))
    mlflow.set_experiment("SilverPilot_ML_Training")

    # Model Hyperparameters
    hyperparams = {
        "n_estimators": 60,
        "learning_rate": 0.03,
        "max_depth": 3,
        "num_leaves": 7,
        "min_child_samples": 10,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 42,
        "verbosity": -1
    }

    # 1. Walk-Forward Time-Series Validation (5 Folds)
    logger.info("Starting Walk-Forward Time-Series Split Validation (5 Folds)...")
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_precisions = []
    fold_recalls = []
    fold_accuracies = []
    fold_bh_win_rates = []

    with mlflow.start_run(run_name="LightGBM_WalkForward_Training") as run:
        run_id = run.info.run_id
        logger.info(f"MLflow Run ID: {run_id}")

        # Log MLflow parameters
        mlflow.log_params(hyperparams)
        mlflow.log_param("features", ",".join(FEATURES))
        mlflow.log_param("target", LABEL)
        mlflow.log_param("dataset_size", len(df))

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            # Train a light, highly regularized/conservative LightGBM model to prevent overfitting
            model = lgb.LGBMClassifier(
                n_estimators=hyperparams["n_estimators"],
                learning_rate=hyperparams["learning_rate"],
                max_depth=hyperparams["max_depth"],
                num_leaves=hyperparams["num_leaves"],
                min_child_samples=hyperparams["min_child_samples"],
                subsample=hyperparams["subsample"],
                colsample_bytree=hyperparams["colsample_bytree"],
                random_state=hyperparams["random_state"],
                verbosity=hyperparams["verbosity"]
            )
            model.fit(X_train, y_train)

            # Make predictions
            y_pred = model.predict(X_test)

            # Calculate metrics
            acc = accuracy_score(y_test, y_pred)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)
            
            # Buy & Hold baseline win rate for this test fold
            bh_win_rate = y_test.mean()

            fold_accuracies.append(acc)
            fold_precisions.append(prec)
            fold_recalls.append(rec)
            fold_bh_win_rates.append(bh_win_rate)

            # Log fold metrics to MLflow
            mlflow.log_metric("fold_accuracy", acc, step=fold)
            mlflow.log_metric("fold_precision", prec, step=fold)
            mlflow.log_metric("fold_recall", rec, step=fold)
            mlflow.log_metric("fold_bh_win_rate", bh_win_rate, step=fold)

            logger.info(
                f"Fold {fold+1} | Train Size: {len(X_train)} | Test Size: {len(X_test)} | "
                f"Accuracy: {acc:.3f} | Model Precision: {prec:.3f} (Karlı Sinyal Hassasiyeti) | "
                f"Recall: {rec:.3f} | B&H Win Rate: {bh_win_rate:.3f}"
            )

        # Average offline metrics
        mean_acc = np.mean(fold_accuracies)
        mean_prec = np.mean(fold_precisions)
        mean_rec = np.mean(fold_recalls)
        mean_bh = np.mean(fold_bh_win_rates)

        # Log aggregated metrics to MLflow
        mlflow.log_metric("mean_accuracy", mean_acc)
        mlflow.log_metric("mean_precision", mean_prec)
        mlflow.log_metric("mean_recall", mean_rec)
        mlflow.log_metric("mean_bh_win_rate", mean_bh)

        logger.info("=== Offline Walk-Forward Validation Summary ===")
        logger.info(f"Mean Accuracy: {mean_acc:.3f}")
        logger.info(f"Mean Model Precision: {mean_prec:.3f} ( karlılık oranı tahmini hassasiyeti )")
        logger.info(f"Mean Recall: {mean_rec:.3f}")
        logger.info(f"Mean Buy & Hold Win Rate: {mean_bh:.3f}")

        if mean_prec > mean_bh:
            logger.info(f"🚀 SUCCESS: Model precision ({mean_prec:.3f}) exceeds Buy & Hold win rate ({mean_bh:.3f})!")
            mlflow.set_tag("performance_status", "PASS")
        else:
            logger.warning(f"⚠️ Model precision ({mean_prec:.3f}) is equal or below Buy & Hold ({mean_bh:.3f}). Keep regularizations high.")
            mlflow.set_tag("performance_status", "WARN")

        # 2. Train Champion Model on ALL data
        logger.info("Training champion model on the entire dataset...")
        champion_model = lgb.LGBMClassifier(
            n_estimators=hyperparams["n_estimators"],
            learning_rate=hyperparams["learning_rate"],
            max_depth=hyperparams["max_depth"],
            num_leaves=hyperparams["num_leaves"],
            min_child_samples=hyperparams["min_child_samples"],
            subsample=hyperparams["subsample"],
            colsample_bytree=hyperparams["colsample_bytree"],
            random_state=hyperparams["random_state"],
            verbosity=hyperparams["verbosity"]
        )
        champion_model.fit(X, y)

        # 3. Save Model Weights & Log to MLflow
        os.makedirs(os.path.dirname(model_output_path), exist_ok=True)
        logger.info(f"Saving model to {model_output_path}...")
        with open(model_output_path, "wb") as f:
            pickle.dump(champion_model, f)
        
        # Log to MLflow Registry
        mlflow.lightgbm.log_model(
            lgb_model=champion_model,
            artifact_path="model",
            registered_model_name="SilverPilot_Champion"
        )
        logger.info("Champion model training, serialization, and MLflow logging completed successfully!")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.dirname(current_dir)
    
    dataset_file = os.path.join(root_path, "data", "datasets", "v1.0.0", "dataset.csv")
    model_file = os.path.join(root_path, "data", "models", "champion_model.pkl")

    train_and_evaluate(dataset_file, model_file)
