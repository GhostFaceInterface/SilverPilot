import ast
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.backtests import BacktestConfig
from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BacktestDatasetSnapshotModel,
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MetalModel,
    MLDatasetSnapshotModel,
    MLExperimentMetricModel,
    MLExperimentRunModel,
    PriceQuoteModel,
    ReferenceMarketInstrumentModel,
    StrategyModel,
    UnitModel,
    UserModel,
    VirtualAccountModel,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.ml_experiments import (
    MLExperimentConfig,
    MLExperimentRunner,
    MLFeatureDatasetBuilder,
    TimeSeriesSplitSpec,
    chronological_splits,
)
from silverpilot.app.paper_trading import PaperCostModel

SOURCE = "reference-fixture"
QUOTE_SOURCE = "kuveyt_turk_finance_portal"
TIMEFRAME = "1h"
START = datetime(2026, 6, 18, 1, 0, tzinfo=UTC)


def test_ml_dataset_is_deterministic_and_cost_label_is_decimal_safe(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session)
        config = _experiment_config(fixture, tmp_path)
        builder = MLFeatureDatasetBuilder(session=session)

        first = builder.build(config=config)
        second = builder.build(config=config)

        assert first.snapshot.data_hash == second.snapshot.data_hash
        assert first.manifest["artifact_hash"] == second.manifest["artifact_hash"]
        assert first.snapshot.row_count == len(first.rows) == 8
        assert first.snapshot.class_balance == {"positive": 4, "negative": 4}
        assert first.manifest["artifact_schema_version"] == "ml-artifact-v2"
        assert first.manifest["advisory_only"] is True
        config_hashes = cast(dict[str, object], first.manifest["config_hashes"])
        model_family_spec = cast(dict[str, object], first.manifest["model_family_spec"])
        model_families = cast(list[dict[str, object]], model_family_spec["families"])
        assert config_hashes["source"] == first.manifest["source_data_hash"]
        assert model_families[0]["advisory_only"] is True
        assert len(list(session.scalars(select(MLDatasetSnapshotModel)))) == 1
        first_row = first.rows[0]
        assert first_row["forward_net_return_after_costs"] == "0.048"
        assert first_row["positive_edge"] is True
        assert Path(str(first.manifest["dataset_uri"])).name == "dataset.csv.gz"
        assert Path(str(first.manifest["manifest_uri"])).name == "manifest.json"


def test_ml_dataset_guards_feature_and_label_time_order(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session)
        config = _experiment_config(fixture, tmp_path)

        result = MLFeatureDatasetBuilder(session=session).build(config=config)

        for row in result.rows:
            decision_at = datetime.fromisoformat(str(row["decision_at"]))
            feature_at = datetime.fromisoformat(str(row["feature_timestamp_max"]))
            entry_quote_at = datetime.fromisoformat(str(row["entry_quote_observed_at"]))
            label_quote_at = datetime.fromisoformat(str(row["label_exit_quote_observed_at"]))
            assert feature_at <= decision_at
            assert entry_quote_at <= decision_at
            assert label_quote_at > decision_at


def test_chronological_splits_apply_embargo() -> None:
    splits = chronological_splits(
        row_count=8,
        spec=TimeSeriesSplitSpec(n_splits=2, embargo_bars=2, min_train_rows=2),
    )

    assert len(splits) == 2
    assert splits[0].train_indices == [0, 1]
    assert splits[0].test_indices == [4, 5]
    assert max(splits[0].train_indices) + 2 < min(splits[0].test_indices)


def test_ml_experiment_runner_persists_advisory_metrics(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session)
        config = _experiment_config(
            fixture,
            tmp_path,
            model_families=("rule_only", "dummy"),
        )

        runs = MLExperimentRunner(session=session).run(config=config)

        assert [run.status for run in runs] == ["completed", "completed"]
        assert all(run.report_json["advisory_only"] is True for run in runs)
        assert all("runtime_boundary" in run.report_json for run in runs)
        assert len(list(session.scalars(select(BacktestDatasetSnapshotModel)))) == 1
        assert len(list(session.scalars(select(MLExperimentRunModel)))) == 2
        metrics = list(session.scalars(select(MLExperimentMetricModel)))
        assert {metric.metric_name for metric in metrics} >= {"accuracy", "precision", "recall"}
        assert session.scalar(
            select(StrategyModel).where(StrategyModel.name == "trend_up_pullback")
        )


def test_ml_experiment_reports_insufficient_data_without_fake_success(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session, bar_count=5)
        config = _experiment_config(fixture, tmp_path, model_families=("dummy",))

        runs = MLExperimentRunner(session=session).run(config=config)

        assert runs[0].status == "insufficient_data"
        assert runs[0].report_json["status"] == "insufficient_data"
        assert list(session.scalars(select(MLExperimentMetricModel))) == []


def test_ml_data_hash_includes_model_family_config(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session)
        rule_only = MLFeatureDatasetBuilder(session=session).build(
            config=_experiment_config(fixture, tmp_path, model_families=("rule_only",))
        )
        dummy = MLFeatureDatasetBuilder(session=session).build(
            config=_experiment_config(fixture, tmp_path, model_families=("dummy",))
        )

        assert rule_only.snapshot.data_hash != dummy.snapshot.data_hash
        rule_only_hashes = cast(dict[str, object], rule_only.manifest["config_hashes"])
        dummy_hashes = cast(dict[str, object], dummy.manifest["config_hashes"])
        assert rule_only_hashes["model_family"] != dummy_hashes["model_family"]


def test_ml_artifact_writer_does_not_emit_model_binaries(tmp_path: Path) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _seed_ml_fixture(session)
        result = MLFeatureDatasetBuilder(session=session).build(
            config=_experiment_config(fixture, tmp_path)
        )

        artifact_dir = Path(str(result.manifest["manifest_uri"])).parent
        banned_suffixes = {".bin", ".joblib", ".onnx", ".pkl", ".pt"}
        assert {path.suffix for path in artifact_dir.rglob("*")}.isdisjoint(banned_suffixes)
        artifact_policy = cast(dict[str, Any], result.manifest["artifact_policy"])
        assert artifact_policy["model_binary_persisted"] is False


def test_runtime_paths_do_not_import_ml_experiments() -> None:
    runtime_roots = [
        Path("src/silverpilot/app/api"),
        Path("src/silverpilot/app/strategies"),
        Path("src/silverpilot/app/risks"),
        Path("src/silverpilot/app/paper_trading"),
        Path("src/silverpilot/app/notifications"),
        Path("src/silverpilot/app/collectors"),
        Path("src/silverpilot/app/backtests"),
    ]
    offenders: list[str] = []
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any("ml_experiments" in name for name in names):
                    offenders.append(str(path))

    assert offenders == []


@dataclass(frozen=True)
class _MLFixture:
    account_id: UUID
    strategy_id: UUID
    reference_instrument_id: UUID
    execution_instrument_id: UUID


def _engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def _experiment_config(
    fixture: _MLFixture,
    tmp_path: Path,
    *,
    model_families: tuple[str, ...] = ("rule_only", "dummy"),
) -> MLExperimentConfig:
    return MLExperimentConfig(
        backtest_config=BacktestConfig(
            strategy_id=fixture.strategy_id,
            base_account_id=fixture.account_id,
            execution_instrument_id=fixture.execution_instrument_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=fixture.reference_instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            quote_source=QUOTE_SOURCE,
            start_at=START,
            end_at=START + timedelta(hours=10),
            initial_cash=Decimal("1000"),
            decision_latency=timedelta(minutes=1),
            cost_model=PaperCostModel(fee_rate=Decimal("0.001"), tax_rate=Decimal("0")),
        ),
        output_root=tmp_path / "mlruns" / "phase14",
        label_horizon_bars=2,
        split_spec=TimeSeriesSplitSpec(n_splits=2, embargo_bars=1, min_train_rows=2),
        model_families=model_families,
    )


def _seed_ml_fixture(session: Session, *, bar_count: int = 10) -> _MLFixture:
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{uuid4().hex[:2]}",
        name="Turkish Lira",
        decimal_places=2,
        created_at=START,
    )
    unit = UnitModel(
        id=uuid4(),
        code=f"G{uuid4().hex[:4]}",
        name="Gram",
        precision=6,
        created_at=START,
    )
    metal = MetalModel(
        id=uuid4(),
        code=f"X{uuid4().hex[:4]}",
        name="Silver",
        default_unit=unit,
        created_at=START,
    )
    bank = BankModel(
        id=uuid4(),
        code=f"bank_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=START,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code=f"venue_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        status="active",
        created_at=START,
    )
    bank_instrument = BankInstrumentModel(
        id=uuid4(),
        bank=bank,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
        status="active",
        created_at=START,
    )
    execution_instrument = ExecutionInstrumentModel(
        id=uuid4(),
        execution_venue=venue,
        bank_instrument=bank_instrument,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        status="active",
        created_at=START,
    )
    reference = ReferenceMarketInstrumentModel(
        id=uuid4(),
        symbol=f"REF-XAG-{uuid4().hex[:6]}",
        source=SOURCE,
        metal=metal,
        currency=currency,
        unit=unit,
        status="active",
        created_at=START,
    )
    user = UserModel(
        id=uuid4(), email=f"{uuid4().hex[:8]}@example.com", status="active", created_at=START
    )
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Live paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("1000"),
        status="active",
        created_at=START,
    )
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": "500"},
        enabled=True,
        created_at=START,
    )
    session.add_all([bank_instrument, execution_instrument, reference, account, strategy])
    bank_buy_prices = [
        Decimal("99"),
        Decimal("100"),
        Decimal("105"),
        Decimal("106"),
        Decimal("107"),
        Decimal("108"),
        Decimal("95"),
        Decimal("94"),
        Decimal("93"),
        Decimal("92"),
    ]
    for offset in range(1, bar_count + 1):
        bar_end_at = START + timedelta(hours=offset)
        _add_market_context(session, reference.id, bar_end_at)
        bank_buy = bank_buy_prices[offset - 1]
        _add_quote(
            session,
            bank_instrument=bank_instrument,
            observed_at=bar_end_at + timedelta(seconds=30),
            bank_buy=bank_buy,
            bank_sell=bank_buy + Decimal("1"),
        )
    session.flush()
    return _MLFixture(
        account_id=account.id,
        strategy_id=strategy.id,
        reference_instrument_id=reference.id,
        execution_instrument_id=execution_instrument.id,
    )


def _add_market_context(session: Session, instrument_id: UUID, bar_end_at: datetime) -> None:
    session.add(
        MarketBarModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            quote_count=1,
            bar_start_at=bar_end_at - timedelta(hours=1),
            bar_end_at=bar_end_at,
            created_at=bar_end_at,
        )
    )
    session.add(
        MarketRegimeSnapshotModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            regime=MarketRegime.TREND_UP.value,
            confidence=Decimal("0.8500"),
            evidence={"candidate_regime": MarketRegime.TREND_UP.value},
            config_version="rule-v1",
            starts_at=bar_end_at,
            confirmed_at=bar_end_at,
            source_bar_end_at=bar_end_at,
            created_at=bar_end_at,
        )
    )
    indicator_inputs: tuple[tuple[str, dict[str, object], Decimal], ...] = (
        ("ema", {"period": 50}, Decimal("100")),
        ("ema", {"period": 200}, Decimal("95")),
        ("rsi", {"period": 14}, Decimal("45")),
        ("atr", {"period": 14}, Decimal("1.2")),
        ("adx", {"period": 14}, Decimal("22")),
        ("bb_width", {"period": 20}, Decimal("0.04")),
    )
    for indicator_name, parameters, value in indicator_inputs:
        session.add(
            IndicatorSnapshotModel(
                instrument_type=InstrumentType.REFERENCE.value,
                instrument_id=instrument_id,
                source=SOURCE,
                timeframe=TIMEFRAME,
                indicator_name=indicator_name,
                parameters_hash=hash_parameters(parameters),
                parameters=parameters,
                value=value,
                calculated_at=bar_end_at,
                source_bar_end_at=bar_end_at,
                created_at=bar_end_at,
            )
        )


def _add_quote(
    session: Session,
    *,
    bank_instrument: BankInstrumentModel,
    observed_at: datetime,
    bank_buy: Decimal,
    bank_sell: Decimal,
) -> None:
    session.add(
        PriceQuoteModel(
            id=uuid4(),
            bank_instrument=bank_instrument,
            bank_buy_price=bank_buy,
            bank_sell_price=bank_sell,
            observed_at=observed_at,
            fetched_at=observed_at,
            source=QUOTE_SOURCE,
            source_hash=f"quote-{observed_at.isoformat()}",
            freshness_status="fresh",
            created_at=observed_at,
        )
    )
