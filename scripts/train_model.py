#!/usr/bin/env python3
"""
SilverPilot ML Model Training Pipeline
Trains a conservative LightGBMClassifier on the offline dataset
using Walk-Forward validation, compares to Buy & Hold, and saves the champion model.
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

    # 1. Walk-Forward Time-Series Validation (5 Folds)
    logger.info("Starting Walk-Forward Time-Series Split Validation (5 Folds)...")
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_precisions = []
    fold_recalls = []
    fold_accuracies = []
    fold_bh_win_rates = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        # Train a light, highly regularized/conservative LightGBM model to prevent overfitting
        model = lgb.LGBMClassifier(
            n_estimators=50,
            learning_rate=0.03,
            max_depth=3,
            num_leaves=7,
            min_child_samples=10,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=-1
        )
        model.fit(X_train, y_train)

        # Make predictions
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        # Calculate metrics
        # Standard classification metrics
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        
        # Buy & Hold baseline win rate for this test fold
        bh_win_rate = y_test.mean()

        fold_accuracies.append(acc)
        fold_precisions.append(prec)
        fold_recalls.append(rec)
        fold_bh_win_rates.append(bh_win_rate)

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

    logger.info("=== Offline Walk-Forward Validation Summary ===")
    logger.info(f"Mean Accuracy: {mean_acc:.3f}")
    logger.info(f"Mean Model Precision: {mean_prec:.3f} ( karlılık oranı tahmini hassasiyeti )")
    logger.info(f"Mean Recall: {mean_rec:.3f}")
    logger.info(f"Mean Buy & Hold Win Rate: {mean_bh:.3f}")

    if mean_prec > mean_bh:
        logger.info(f"🚀 SUCCESS: Model precision ({mean_prec:.3f}) exceeds Buy & Hold win rate ({mean_bh:.3f})!")
    else:
        logger.warning(f"⚠️ Model precision ({mean_prec:.3f}) is equal or below Buy & Hold ({mean_bh:.3f}). Keep regularizations high.")

    # 2. Train Champion Model on ALL data
    logger.info("Training champion model on the entire dataset...")
    champion_model = lgb.LGBMClassifier(
        n_estimators=60,
        learning_rate=0.03,
        max_depth=3,
        num_leaves=7,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=-1
    )
    champion_model.fit(X, y)

    # 3. Save Model Weights
    os.makedirs(os.path.dirname(model_output_path), exist_ok=True)
    logger.info(f"Saving model to {model_output_path}...")
    with open(model_output_path, "wb") as f:
        pickle.dump(champion_model, f)
    
    logger.info("Champion model training and serialization completed successfully!")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.dirname(current_dir)
    
    dataset_file = os.path.join(root_path, "data", "datasets", "v1.0.0", "dataset.csv")
    model_file = os.path.join(root_path, "data", "models", "champion_model.pkl")

    train_and_evaluate(dataset_file, model_file)
