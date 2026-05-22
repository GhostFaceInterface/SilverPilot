# Implementation Plan: Phase 9 - ML Dataset Automation

This plan outlines the design and implementation of the ML Dataset Automation pipeline for SilverPilot. It ensures zero-leakage feature generation, robust future label calculations, secure FastAPI integration, and high test coverage under SQLite.

---

## 🛡️ Risk & Context Analysis
- **Zero-Leakage Requirement:** Features must only look backward or at the exact present moment of `observed_at`. Labels look into the future.
- **Off-VPS ML Training Rule:** Do not write training routines. Focus entirely on dataset generation.
- **Access Control:** The API endpoints must be fully secured using the `verify_agent_token` dependency.
- **Affected Files:**
  - `scripts/build_dataset.py` *[NEW]*: Main pipeline script.
  - `apps/api/app/api/routes.py`: API endpoints integration.
  - `apps/api/tests/test_dataset.py` *[NEW]*: Unit and integration tests.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Dataset Pipeline & Core Utility Builder**
  - [x] Implement `scripts/build_dataset.py` with full type hints, docstrings, and a CLI parser supporting `--dry-run` and `--version` (Ajan: `data-engineer`).
  - [x] **Feature Engineering (Strict Zero-Leakage):**
    - `bank_spread_percent`: PriceSnapshot `spread_percent` if not null/zero, else `(buy_price - sell_price) / mid_price`.
    - `xag_return_15m`, `xag_return_1h`, `xag_return_24h` using historical lookbacks.
    - `usd_try_return_24h` from `RawFxRate` table (USD/TRY).
    - `volatility_24h`, `volatility_7d`: rolling standard deviation of 15m returns over past 24 hours/7 days.
    - `xau_xag_ratio`: closest `TechnicalIndicator.xau_xag_ratio` prior to or equal to `observed_at`.
    - `news_sentiment_score`: closest sentiment from `HistoricalAgentCache` or `AgentMemoryEvent` (within last 24h). Map BULLISH=1.0, NEUTRAL=0.0, BEARISH=-1.0. Default = 0.0.
    - `hour_of_day`, `day_of_week` (UTC).
  - [x] **Labels Calculation (Future-Looking):**
    - `net_profit_1d`, `net_profit_3d`, `net_profit_7d` returns.
    - `profitable_after_costs_3d`: binary 1 if future `sell_price(t + 3d) > buy_price(t)` else 0.
    - `max_drawdown_3d`: max peak-to-trough drop from current `mid_price` over next 3 days.
  - [x] Save to `data/datasets/v{version}/dataset.parquet` and `dataset.csv`. Write `metadata.json` detailing row counts, features, and timestamps.
  - *DoD (Tamamlanma Tanımı):* `python scripts/build_dataset.py --dry-run --version 1.0.0` runs successfully and demonstrates correct feature calculations on local DB.
 
- `[x]` **Faz 2: Dataset API Integration & Security**
  - [x] Add `POST /datasets/build` protected by `verify_agent_token` executing the dataset builder in `BackgroundTasks` (Ajan: `backend-architect`).
  - [x] Add `GET /datasets/list` protected by `verify_agent_token` returning metadata of created datasets under `data/datasets/`.
  - *DoD:* FastAPI starts and routes are accessible under API docs with X-Agent-Token authorization required.
 
- `[x]` **Faz 3: Quality Control & Pytest Validation**
  - [x] Create `apps/api/tests/test_dataset.py` test suite (Ajan: `quality-engineer`).
  - [x] Test features to ensure absolute zero future-lookahead leakage.
  - [x] Test correct calculation of `profitable_after_costs_3d` and `max_drawdown_3d`.
  - [x] Test that endpoints return 401 Unauthorized without a valid `X-Agent-Token` header.
  - *DoD:* Running `pytest apps/api/tests/test_dataset.py` passes with 100% success.

---

## ❓ Open Questions & Decisions
> [!NOTE]
> 1. **Time-series Matching Tolerance:** When looking up `RawFxRate` or `TechnicalIndicator` values at exact historical points, we will use a rolling historical matching approach (i.e. `pandas.merge_asof` with direction="backward") to ensure zero look-ahead and robust matching.
> 2. **Max Drawdown Calculation:** We will compute max drawdown as the maximum peak-to-trough decline (as a positive float, e.g. `0.05` for a 5% drop) in the 3-day future window.
