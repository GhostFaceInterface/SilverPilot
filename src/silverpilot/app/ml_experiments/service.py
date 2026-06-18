import csv
import gzip
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.backtests import BacktestConfig, BacktestDatasetSnapshotService
from silverpilot.app.db.models import (
    EventRiskSnapshotModel,
    ExecutionInstrumentModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MLDatasetSnapshotModel,
    MLExperimentMetricModel,
    MLExperimentRunModel,
    PriceQuoteModel,
    StrategyModel,
)
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.paper_trading import PaperCostModel
from silverpilot.app.strategies import TrendUpPullbackConfig, evaluate_trend_up_pullback
from silverpilot.app.strategies.service import _IndicatorLookup

_FEATURE_SPEC_VERSION = "phase14_v1"
_LABEL_SPEC_VERSION = "forward_net_return_after_costs_v1"
_REQUIRED_INDICATORS: dict[str, tuple[str, dict[str, object]]] = {
    "ema_50": ("ema", {"period": 50}),
    "ema_200": ("ema", {"period": 200}),
    "rsi_14": ("rsi", {"period": 14}),
    "atr_14": ("atr", {"period": 14}),
}
_OPTIONAL_INDICATORS: dict[str, tuple[str, dict[str, object]]] = {
    "adx_14": ("adx", {"period": 14}),
    "bb_width": ("bb_width", {"period": 20}),
}
_METRIC_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True)
class TimeSeriesSplitSpec:
    n_splits: int = 3
    embargo_bars: int = 4
    min_train_rows: int = 4
    min_test_rows: int = 1

    def __post_init__(self) -> None:
        if self.n_splits <= 0:
            raise ValueError("n_splits must be greater than zero")
        if self.embargo_bars < 0:
            raise ValueError("embargo_bars cannot be negative")
        if self.min_train_rows <= 0:
            raise ValueError("min_train_rows must be greater than zero")
        if self.min_test_rows <= 0:
            raise ValueError("min_test_rows must be greater than zero")


@dataclass(frozen=True)
class MLExperimentConfig:
    backtest_config: BacktestConfig
    output_root: Path = Path("mlruns/phase14")
    label_horizon_bars: int = 4
    min_edge_bps: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    split_spec: TimeSeriesSplitSpec | None = None
    random_seed: int = 42
    model_families: tuple[str, ...] = ("rule_only", "dummy", "logistic_regression")
    strategy_config: TrendUpPullbackConfig | None = None

    def __post_init__(self) -> None:
        if self.label_horizon_bars <= 0:
            raise ValueError("label_horizon_bars must be greater than zero")
        if self.min_edge_bps < Decimal("0"):
            raise ValueError("min_edge_bps cannot be negative")
        if self.slippage_bps < Decimal("0"):
            raise ValueError("slippage_bps cannot be negative")
        if not self.model_families:
            raise ValueError("model_families is required")


@dataclass(frozen=True)
class MLDatasetBuildResult:
    snapshot: MLDatasetSnapshotModel
    rows: list[dict[str, object]]
    manifest: dict[str, object]


@dataclass(frozen=True)
class _Split:
    name: str
    train_indices: list[int]
    test_indices: list[int]


class MLFeatureDatasetBuilder:
    """Builds Phase 14 offline candidate rows without mutating runtime trading state."""

    def __init__(
        self,
        *,
        session: Session,
        artifact_writer: "MLArtifactWriter | None" = None,
    ) -> None:
        self._session = session
        self._artifact_writer = artifact_writer or MLArtifactWriter()

    def build(self, *, config: MLExperimentConfig) -> MLDatasetBuildResult:
        source_snapshot = (
            BacktestDatasetSnapshotService(session=self._session)
            .create(config=config.backtest_config)
            .snapshot
        )
        rows = self._candidate_rows(config=config)
        feature_spec = _feature_spec()
        label_spec = _label_spec(config)
        split_spec = _split_spec(config)
        class_balance = _class_balance(rows)
        data_hash = _hash_json(
            {
                "source_data_hash": source_snapshot.data_hash,
                "feature_spec": feature_spec,
                "label_spec": label_spec,
                "split_spec": split_spec,
                "rows": rows,
            }
        )
        artifact = self._artifact_writer.write(
            rows=rows,
            data_hash=data_hash,
            manifest={
                "phase": "phase14",
                "source_dataset_snapshot_id": str(source_snapshot.id),
                "source_data_hash": source_snapshot.data_hash,
                "feature_spec": feature_spec,
                "label_spec": label_spec,
                "split_spec": split_spec,
                "row_count": len(rows),
                "class_balance": class_balance,
                "data_hash": data_hash,
            },
            output_root=config.output_root,
        )
        existing = self._session.scalar(
            select(MLDatasetSnapshotModel).where(MLDatasetSnapshotModel.data_hash == data_hash)
        )
        if existing is not None:
            return MLDatasetBuildResult(snapshot=existing, rows=rows, manifest=artifact)

        snapshot = MLDatasetSnapshotModel(
            id=uuid4(),
            source_dataset_snapshot_id=source_snapshot.id,
            feature_spec=feature_spec,
            label_spec=label_spec,
            split_spec=split_spec,
            start_at=config.backtest_config.start_at.astimezone(UTC),
            end_at=config.backtest_config.end_at.astimezone(UTC),
            row_count=len(rows),
            class_balance=class_balance,
            artifact_uri=str(artifact["dataset_uri"]),
            artifact_hash=str(artifact["artifact_hash"]),
            data_hash=data_hash,
            created_at=datetime.now(UTC),
        )
        self._session.add(snapshot)
        self._session.flush()
        return MLDatasetBuildResult(snapshot=snapshot, rows=rows, manifest=artifact)

    def _candidate_rows(self, *, config: MLExperimentConfig) -> list[dict[str, object]]:
        backtest_config = config.backtest_config
        strategy = self._session.get(StrategyModel, backtest_config.strategy_id)
        if strategy is None:
            raise ValueError(f"strategy was not found: {backtest_config.strategy_id}")
        bank_instrument_id = _bank_instrument_id(
            self._session, backtest_config.execution_instrument_id
        )
        bars = list(
            self._session.scalars(
                select(MarketBarModel)
                .where(
                    MarketBarModel.instrument_type == backtest_config.instrument_type.value,
                    MarketBarModel.instrument_id == backtest_config.instrument_id,
                    MarketBarModel.source == backtest_config.source,
                    MarketBarModel.timeframe == backtest_config.timeframe,
                    MarketBarModel.bar_end_at >= backtest_config.start_at,
                    MarketBarModel.bar_end_at <= backtest_config.end_at,
                )
                .order_by(MarketBarModel.bar_end_at, MarketBarModel.id)
            )
        )
        rows: list[dict[str, object]] = []
        for index, bar in enumerate(bars):
            decision_at = _aware_utc(bar.bar_end_at) + backtest_config.decision_latency
            indicators, indicator_rows = self._indicator_lookup(config=backtest_config, bar=bar)
            regime = self._regime(config=backtest_config, bar=bar)
            if not _feature_times_are_known(
                decision_at=decision_at,
                bar=bar,
                regime=regime,
                indicator_rows=indicator_rows,
            ):
                continue
            decision = evaluate_trend_up_pullback(
                strategy=strategy,
                bar=bar,
                regime=regime,
                indicators=indicators,
                source_bar_end_at=_aware_utc(bar.bar_end_at),
                run_at=decision_at,
                config=config.strategy_config,
            )
            if not decision.create_intent:
                continue
            entry_quote = _latest_quote(
                self._session,
                bank_instrument_id=bank_instrument_id,
                source=backtest_config.quote_source,
                observed_lte=decision_at,
            )
            if entry_quote is None:
                continue
            horizon_index = index + config.label_horizon_bars
            if horizon_index >= len(bars):
                continue
            label_at = _aware_utc(bars[horizon_index].bar_end_at) + backtest_config.decision_latency
            exit_quote = _latest_quote(
                self._session,
                bank_instrument_id=bank_instrument_id,
                source=backtest_config.quote_source,
                observed_lte=label_at,
                observed_gt=decision_at,
            )
            if exit_quote is None:
                continue
            row = self._row(
                config=config,
                bar=bar,
                regime=regime,
                indicators=indicators.values,
                indicator_rows=indicator_rows,
                entry_quote=entry_quote,
                exit_quote=exit_quote,
                decision_at=decision_at,
                label_at=label_at,
            )
            rows.append(row)
        return rows

    def _row(
        self,
        *,
        config: MLExperimentConfig,
        bar: MarketBarModel,
        regime: MarketRegimeSnapshotModel | None,
        indicators: dict[str, Decimal],
        indicator_rows: list[IndicatorSnapshotModel],
        entry_quote: PriceQuoteModel,
        exit_quote: PriceQuoteModel,
        decision_at: datetime,
        label_at: datetime,
    ) -> dict[str, object]:
        cost_model = config.backtest_config.cost_model or PaperCostModel()
        forward_return = _forward_net_return_after_costs(
            entry_sell=Decimal(entry_quote.bank_sell_price),
            exit_buy=Decimal(exit_quote.bank_buy_price),
            cost_model=cost_model,
            slippage_bps=config.slippage_bps,
        )
        min_edge = config.min_edge_bps / Decimal("10000")
        close = Decimal(bar.close)
        ema_50 = indicators["ema_50"]
        ema_200 = indicators["ema_200"]
        spread_pct = _spread_pct(entry_quote)
        active_risk = self._active_event_risk(decision_at=decision_at)
        return {
            "source_bar_end_at": _iso(bar.bar_end_at),
            "decision_at": _iso(decision_at),
            "label_at": _iso(label_at),
            "label_exit_quote_observed_at": _iso(exit_quote.observed_at),
            "bar_close": str(close),
            "ema_50": str(ema_50),
            "ema_200": str(ema_200),
            "rsi_14": str(indicators["rsi_14"]),
            "atr_14": str(indicators["atr_14"]),
            "adx_14": _optional_decimal(indicators.get("adx_14")),
            "bb_width": _optional_decimal(indicators.get("bb_width")),
            "close_over_ema_50": str(_ratio(close, ema_50)),
            "close_over_ema_200": str(_ratio(close, ema_200)),
            "ema_50_over_ema_200": str(_ratio(ema_50, ema_200)),
            "regime": regime.regime if regime is not None else "",
            "regime_confidence": str(regime.confidence if regime is not None else Decimal("0")),
            "bank_spread_pct": str(spread_pct),
            "quote_age_seconds": int(
                (decision_at - _aware_utc(entry_quote.observed_at)).total_seconds()
            ),
            "active_event_risk_count": active_risk["count"],
            "active_event_risk_high_count": active_risk["high_count"],
            "active_event_risk_veto_count": active_risk["veto_count"],
            "entry_bank_sell_price": str(entry_quote.bank_sell_price),
            "exit_bank_buy_price": str(exit_quote.bank_buy_price),
            "forward_net_return_after_costs": str(forward_return),
            "positive_edge": forward_return > min_edge,
            "feature_timestamp_max": _iso(
                max(
                    [
                        _aware_utc(bar.bar_end_at),
                        *[_aware_utc(row.calculated_at) for row in indicator_rows],
                    ]
                )
            ),
            "entry_quote_observed_at": _iso(entry_quote.observed_at),
        }

    def _indicator_lookup(
        self,
        *,
        config: BacktestConfig,
        bar: MarketBarModel,
    ) -> tuple[_IndicatorLookup, list[IndicatorSnapshotModel]]:
        snapshots = list(
            self._session.scalars(
                select(IndicatorSnapshotModel).where(
                    IndicatorSnapshotModel.instrument_type == config.instrument_type.value,
                    IndicatorSnapshotModel.instrument_id == config.instrument_id,
                    IndicatorSnapshotModel.source == config.source,
                    IndicatorSnapshotModel.timeframe == config.timeframe,
                    IndicatorSnapshotModel.source_bar_end_at == bar.bar_end_at,
                )
            )
        )
        values: dict[str, Decimal] = {}
        missing: list[str] = []
        used_rows: list[IndicatorSnapshotModel] = []
        for key, (name, parameters) in {**_REQUIRED_INDICATORS, **_OPTIONAL_INDICATORS}.items():
            snapshot = _find_indicator_snapshot(snapshots, name, parameters)
            if snapshot is None:
                if key in _REQUIRED_INDICATORS:
                    missing.append(key)
                continue
            values[key] = Decimal(snapshot.value)
            used_rows.append(snapshot)
        return _IndicatorLookup(values=values, missing=missing), used_rows

    def _regime(
        self,
        *,
        config: BacktestConfig,
        bar: MarketBarModel,
    ) -> MarketRegimeSnapshotModel | None:
        return self._session.scalar(
            select(MarketRegimeSnapshotModel).where(
                MarketRegimeSnapshotModel.instrument_type == config.instrument_type.value,
                MarketRegimeSnapshotModel.instrument_id == config.instrument_id,
                MarketRegimeSnapshotModel.source == config.source,
                MarketRegimeSnapshotModel.timeframe == config.timeframe,
                MarketRegimeSnapshotModel.source_bar_end_at == bar.bar_end_at,
            )
        )

    def _active_event_risk(self, *, decision_at: datetime) -> dict[str, int]:
        snapshots = list(
            self._session.scalars(
                select(EventRiskSnapshotModel).where(
                    EventRiskSnapshotModel.interpreted_at <= decision_at,
                    EventRiskSnapshotModel.expires_at > decision_at,
                )
            )
        )
        return {
            "count": len(snapshots),
            "high_count": sum(1 for row in snapshots if row.risk_level == "high"),
            "veto_count": sum(1 for row in snapshots if row.action_recommendation == "veto"),
        }


class MLArtifactWriter:
    def write(
        self,
        *,
        rows: list[dict[str, object]],
        data_hash: str,
        manifest: dict[str, object],
        output_root: Path,
    ) -> dict[str, object]:
        artifact_dir = output_root / data_hash
        artifact_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = artifact_dir / "dataset.csv.gz"
        fieldnames = sorted({key for row in rows for key in row})
        with (
            dataset_path.open("wb") as raw_handle,
            gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as gzip_handle,
            io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="") as handle,
        ):
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        artifact_hash = _file_sha256(dataset_path)
        full_manifest = {
            **manifest,
            "dataset_uri": str(dataset_path),
            "artifact_hash": artifact_hash,
            "manifest_uri": str(artifact_dir / "manifest.json"),
            "artifact_policy": {
                "model_binary_persisted": False,
                "row_level_database_storage": False,
                "raw_provider_payloads": False,
            },
        }
        manifest_path = artifact_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(full_manifest, sort_keys=True, indent=2, default=_json_value),
            encoding="utf-8",
        )
        return full_manifest


class MLExperimentRunner:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def run(self, *, config: MLExperimentConfig) -> list[MLExperimentRunModel]:
        dataset = MLFeatureDatasetBuilder(session=self._session).build(config=config)
        runs: list[MLExperimentRunModel] = []
        for model_family in config.model_families:
            runs.append(self._run_model(model_family=model_family, config=config, dataset=dataset))
        return runs

    def _run_model(
        self,
        *,
        model_family: str,
        config: MLExperimentConfig,
        dataset: MLDatasetBuildResult,
    ) -> MLExperimentRunModel:
        started_at = datetime.now(UTC)
        run = MLExperimentRunModel(
            id=uuid4(),
            dataset_snapshot_id=dataset.snapshot.id,
            model_family=model_family,
            hyperparameters=_hyperparameters(model_family),
            random_seed=config.random_seed,
            status="insufficient_data",
            started_at=started_at,
            completed_at=None,
            report_json={"status": "running"},
            created_at=started_at,
        )
        self._session.add(run)
        self._session.flush()
        splits = chronological_splits(
            row_count=len(dataset.rows),
            spec=config.split_spec or TimeSeriesSplitSpec(embargo_bars=config.label_horizon_bars),
        )
        labels = [bool(row["positive_edge"]) for row in dataset.rows]
        if not splits or len(set(labels)) < 2:
            run.status = "insufficient_data"
            run.completed_at = datetime.now(UTC)
            run.report_json = {
                "status": "insufficient_data",
                "reason": "not enough chronological rows or label classes",
                "row_count": len(dataset.rows),
                "class_balance": dataset.snapshot.class_balance,
            }
            self._session.flush()
            return run

        try:
            fold_reports = []
            for split in splits:
                predictions = _predict(
                    model_family=model_family,
                    rows=dataset.rows,
                    labels=labels,
                    split=split,
                    random_seed=config.random_seed,
                )
                metrics = _classification_metrics(
                    actual=[labels[index] for index in split.test_indices],
                    predicted=predictions,
                )
                fold_reports.append(
                    {
                        "split": split.name,
                        "metrics": {key: str(value) for key, value in metrics.items()},
                    }
                )
                for metric_name, metric_value in metrics.items():
                    self._session.add(
                        MLExperimentMetricModel(
                            id=uuid4(),
                            experiment_run_id=run.id,
                            split=split.name,
                            metric_name=metric_name,
                            metric_value=Decimal(str(metric_value)).quantize(_METRIC_QUANTUM),
                            metric_metadata={
                                "train_rows": len(split.train_indices),
                                "test_rows": len(split.test_indices),
                            },
                            created_at=started_at,
                        )
                    )
            run.status = "completed"
            run.report_json = {
                "status": "completed",
                "model_family": model_family,
                "advisory_only": True,
                "folds": fold_reports,
                "promotion_gate": "compare against rule_only baseline before any runtime ML task",
            }
        except (ImportError, ValueError) as exc:
            run.status = "failed"
            run.report_json = {"status": "failed", "error": str(exc), "advisory_only": True}
        run.completed_at = datetime.now(UTC)
        self._session.flush()
        return run


def chronological_splits(*, row_count: int, spec: TimeSeriesSplitSpec) -> list[_Split]:
    test_size = max(spec.min_test_rows, row_count // (spec.n_splits + 1))
    splits: list[_Split] = []
    for fold in range(spec.n_splits):
        train_end = test_size * (fold + 1)
        test_start = train_end + spec.embargo_bars
        test_end = test_start + test_size
        if train_end < spec.min_train_rows or test_end > row_count:
            continue
        splits.append(
            _Split(
                name=f"fold_{fold + 1}",
                train_indices=list(range(0, train_end)),
                test_indices=list(range(test_start, test_end)),
            )
        )
    return splits


def _predict(
    *,
    model_family: str,
    rows: list[dict[str, object]],
    labels: list[bool],
    split: _Split,
    random_seed: int,
) -> list[bool]:
    train_labels = [labels[index] for index in split.train_indices]
    if model_family == "rule_only":
        return [True for _ in split.test_indices]
    if model_family == "dummy":
        majority = sum(train_labels) >= (len(train_labels) / 2)
        return [majority for _ in split.test_indices]
    if model_family == "logistic_regression":
        if len(set(train_labels)) < 2:
            raise ValueError("logistic_regression requires both classes in the training split")
        from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

        model = LogisticRegression(random_state=random_seed, max_iter=1000)
        model.fit(_matrix(rows, split.train_indices), train_labels)
        return [bool(value) for value in model.predict(_matrix(rows, split.test_indices))]
    raise ValueError(f"unsupported model family: {model_family}")


def _matrix(rows: list[dict[str, object]], indices: list[int]) -> list[list[float]]:
    feature_names = [
        "bar_close",
        "ema_50",
        "ema_200",
        "rsi_14",
        "atr_14",
        "adx_14",
        "bb_width",
        "close_over_ema_50",
        "close_over_ema_200",
        "ema_50_over_ema_200",
        "regime_confidence",
        "bank_spread_pct",
        "quote_age_seconds",
        "active_event_risk_count",
        "active_event_risk_high_count",
        "active_event_risk_veto_count",
    ]
    return [[_float_feature(rows[index].get(name)) for name in feature_names] for index in indices]


def _classification_metrics(*, actual: list[bool], predicted: list[bool]) -> dict[str, Decimal]:
    tp = sum(1 for real, pred in zip(actual, predicted, strict=True) if real and pred)
    tn = sum(1 for real, pred in zip(actual, predicted, strict=True) if not real and not pred)
    fp = sum(1 for real, pred in zip(actual, predicted, strict=True) if not real and pred)
    fn = sum(1 for real, pred in zip(actual, predicted, strict=True) if real and not pred)
    total = len(actual)
    return {
        "accuracy": _safe_ratio(Decimal(tp + tn), Decimal(total)),
        "precision": _safe_ratio(Decimal(tp), Decimal(tp + fp)),
        "recall": _safe_ratio(Decimal(tp), Decimal(tp + fn)),
        "positive_rate": _safe_ratio(Decimal(sum(predicted)), Decimal(total)),
    }


def _float_feature(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(str(value))


def _feature_spec() -> dict[str, object]:
    return {
        "version": _FEATURE_SPEC_VERSION,
        "candidate_universe": "trend_up_pullback_buy_intents",
        "features": [
            "ema_50",
            "ema_200",
            "rsi_14",
            "atr_14",
            "adx_14",
            "bb_width",
            "close_over_ema_50",
            "close_over_ema_200",
            "ema_50_over_ema_200",
            "regime",
            "regime_confidence",
            "bank_spread_pct",
            "quote_age_seconds",
            "active_event_risk_count",
            "active_event_risk_high_count",
            "active_event_risk_veto_count",
        ],
        "timestamp_rule": "feature timestamps must be <= decision_at",
    }


def _label_spec(config: MLExperimentConfig) -> dict[str, object]:
    cost_model = config.backtest_config.cost_model or PaperCostModel()
    return {
        "version": _LABEL_SPEC_VERSION,
        "label": "forward_net_return_after_costs",
        "positive_edge_rule": "forward_net_return_after_costs > min_edge_bps / 10000",
        "label_horizon_bars": config.label_horizon_bars,
        "min_edge_bps": str(config.min_edge_bps),
        "slippage_bps": str(config.slippage_bps),
        "fee_rate": str(cost_model.fee_rate),
        "tax_rate": str(cost_model.tax_rate),
        "entry_price": "latest bank_sell_price at decision_at",
        "exit_price": "latest bank_buy_price after decision_at through horizon end",
    }


def _split_spec(config: MLExperimentConfig) -> dict[str, object]:
    spec = config.split_spec or TimeSeriesSplitSpec(embargo_bars=config.label_horizon_bars)
    return {"strategy": "chronological_expanding_window", **asdict(spec)}


def _class_balance(rows: list[dict[str, object]]) -> dict[str, object]:
    positives = sum(1 for row in rows if bool(row["positive_edge"]))
    negatives = len(rows) - positives
    return {"positive": positives, "negative": negatives}


def _forward_net_return_after_costs(
    *,
    entry_sell: Decimal,
    exit_buy: Decimal,
    cost_model: PaperCostModel,
    slippage_bps: Decimal,
) -> Decimal:
    if entry_sell <= Decimal("0"):
        raise ValueError("entry_sell must be positive")
    round_trip_cost_rate = (cost_model.fee_rate + cost_model.tax_rate) * Decimal("2")
    slippage_rate = slippage_bps / Decimal("10000")
    return ((exit_buy - entry_sell) / entry_sell) - round_trip_cost_rate - slippage_rate


def _latest_quote(
    session: Session,
    *,
    bank_instrument_id: UUID,
    source: str,
    observed_lte: datetime,
    observed_gt: datetime | None = None,
) -> PriceQuoteModel | None:
    query = select(PriceQuoteModel).where(
        PriceQuoteModel.bank_instrument_id == bank_instrument_id,
        PriceQuoteModel.source == source,
        PriceQuoteModel.observed_at <= observed_lte,
    )
    if observed_gt is not None:
        query = query.where(PriceQuoteModel.observed_at > observed_gt)
    return session.scalar(
        query.order_by(PriceQuoteModel.observed_at.desc(), PriceQuoteModel.fetched_at.desc())
    )


def _bank_instrument_id(session: Session, execution_instrument_id: UUID) -> UUID:
    execution_instrument = session.get(ExecutionInstrumentModel, execution_instrument_id)
    if execution_instrument is None or execution_instrument.bank_instrument_id is None:
        raise ValueError("execution instrument has no bank instrument")
    return execution_instrument.bank_instrument_id


def _find_indicator_snapshot(
    snapshots: list[IndicatorSnapshotModel],
    indicator_name: str,
    parameters: dict[str, object],
) -> IndicatorSnapshotModel | None:
    parameters_hash = hash_parameters(parameters)
    for snapshot in snapshots:
        if (
            snapshot.indicator_name == indicator_name
            and snapshot.parameters_hash == parameters_hash
        ):
            return snapshot
    return None


def _feature_times_are_known(
    *,
    decision_at: datetime,
    bar: MarketBarModel,
    regime: MarketRegimeSnapshotModel | None,
    indicator_rows: list[IndicatorSnapshotModel],
) -> bool:
    if _aware_utc(bar.bar_end_at) > decision_at:
        return False
    if regime is not None and _aware_utc(regime.confirmed_at) > decision_at:
        return False
    return all(_aware_utc(row.calculated_at) <= decision_at for row in indicator_rows)


def _spread_pct(quote: PriceQuoteModel) -> Decimal:
    buy = Decimal(quote.bank_buy_price)
    sell = Decimal(quote.bank_sell_price)
    midpoint = (buy + sell) / Decimal("2")
    return Decimal("0") if midpoint == Decimal("0") else (sell - buy) / midpoint


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    return Decimal("0") if denominator == Decimal("0") else numerator / denominator


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    return Decimal("0") if denominator == Decimal("0") else numerator / denominator


def _optional_decimal(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_json(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hyperparameters(model_family: str) -> dict[str, object]:
    if model_family == "logistic_regression":
        return {"max_iter": 1000}
    if model_family == "dummy":
        return {"strategy": "most_frequent"}
    if model_family == "rule_only":
        return {"prediction": "always_positive_for_rule_candidates"}
    return {}


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value


def _iso(value: datetime) -> str:
    return _aware_utc(value).isoformat()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
