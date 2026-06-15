from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import create_app
from app.models import Asset, MarketBar, PriceSnapshot, TechnicalIndicator
from app.services.indicator_readiness import get_indicator_readiness


def _seed_indicator_series(
    db_session, *, count: int, source: str = "yahoo-si-f", timeframe: str = "5m", start: datetime
):
    asset = db_session.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
    if asset is None:
        asset = Asset(symbol="XAG_GRAM", name="Gram Silver", asset_type="metal", is_active=True)
        db_session.add(asset)
        db_session.flush()

    indicators = []
    for idx in range(count):
        observed_at = start + timedelta(minutes=5 * idx)
        price = Decimal("25.00") + Decimal(str(idx)) / Decimal("10")
        snapshot = PriceSnapshot(
            asset_id=asset.id,
            source=source,
            buy_price=price + Decimal("0.05"),
            sell_price=price - Decimal("0.05"),
            mid_price=price,
            currency="USD",
            spread_absolute=Decimal("0.10"),
            spread_percent=Decimal("0.40"),
            observed_at=observed_at,
        )
        db_session.add(snapshot)
        db_session.flush()

        bar_start = observed_at.replace(second=0, microsecond=0)
        market_bar = MarketBar(
            asset_id=asset.id,
            source=source,
            timeframe=timeframe,
            bar_start_at=bar_start,
            bar_end_at=bar_start + timedelta(minutes=5),
            open=price,
            high=price + Decimal("0.2"),
            low=price - Decimal("0.2"),
            close=price,
            currency="USD",
            sample_count=1,
            first_price_snapshot_id=snapshot.id,
            last_price_snapshot_id=snapshot.id,
            quality_status="ok",
            bar_builder_version="market-bars-v1",
        )
        db_session.add(market_bar)
        db_session.flush()

        indicator = TechnicalIndicator(
            price_snapshot_id=snapshot.id,
            market_bar_id=market_bar.id,
            bar_timestamp=bar_start,
            timeframe=timeframe,
            calculation_version="technical-indicators-v2",
            input_bar_count=idx + 1,
            quality_status="ok",
            close_usd_oz=price,
            rsi_14=Decimal("45.0"),
            macd_line=Decimal("0.1000"),
            macd_signal=Decimal("0.0500"),
            macd_histogram=Decimal("0.0500"),
            bb_upper_20_2=price + Decimal("1.5"),
            bb_middle_20_2=price,
            bb_lower_20_2=price - Decimal("1.5"),
            sma_20=price - Decimal("0.2"),
            sma_50=price - Decimal("0.5"),
            ema_20=price - Decimal("0.1"),
            ema_50=price - Decimal("0.3"),
            ema_200=price - Decimal("0.8"),
            adx_14=Decimal("20.0"),
            plus_di_14=Decimal("22.0"),
            minus_di_14=Decimal("18.0"),
            bb_bandwidth_20_2=Decimal("0.12"),
            bb_percent_b_20_2=Decimal("0.55"),
            atr_14=Decimal("0.3"),
            atr_percent_14=Decimal("0.012"),
            rsi_slope_1=Decimal("0.5"),
            macd_histogram_slope_1=Decimal("0.01"),
        )
        db_session.add(indicator)
        indicators.append(indicator)

    db_session.commit()
    return asset, indicators


def test_indicator_readiness_ready(db_session):
    start = datetime.now(UTC) - timedelta(minutes=5 * 60)
    _, indicators = _seed_indicator_series(db_session, count=50, start=start)

    readiness = get_indicator_readiness(db_session)
    assert readiness.usable is True
    assert readiness.status == "ready"
    assert readiness.indicator_id == indicators[-1].id
    assert readiness.source == "yahoo-si-f"
    assert readiness.input_bar_count == 50
    assert readiness.missing_required_fields == []


def test_indicator_readiness_warmup(db_session):
    start = datetime.now(UTC) - timedelta(minutes=5 * 10)
    _seed_indicator_series(db_session, count=5, start=start)

    readiness = get_indicator_readiness(db_session)
    assert readiness.usable is False
    assert readiness.status == "warming_up"
    assert "INSUFFICIENT_HISTORY" in readiness.reason_codes


def test_low_1d_input_bar_count_keeps_daily_trend_missing(db_session):
    start = datetime.now(UTC) - timedelta(minutes=5 * 10)
    _seed_indicator_series(db_session, count=10, timeframe="1d", start=start)

    readiness = get_indicator_readiness(
        db_session,
        asset_symbol="XAG_GRAM",
        timeframe="1d",
        required_min_bar_count=50,
        max_age_minutes=48 * 60,
    )
    assert readiness.usable is False
    assert readiness.status == "warming_up"
    assert "INSUFFICIENT_HISTORY" in readiness.reason_codes


def test_indicator_readiness_route(db_session):
    start = datetime.now(UTC) - timedelta(minutes=5 * 60)
    _seed_indicator_series(db_session, count=50, start=start)

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/indicators/readiness", params={"asset_symbol": "XAG_GRAM", "timeframe": "5m"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["usable"] is True
    assert payload["status"] == "ready"
    assert payload["asset_symbol"] == "XAG_GRAM"


def test_indicator_readiness_route_includes_strategy_policy(db_session):
    now = datetime.now(UTC)
    _seed_indicator_series(db_session, count=1, timeframe="1d", start=now - timedelta(hours=24))
    _seed_indicator_series(db_session, count=1, timeframe="1h", start=now - timedelta(hours=2))
    _seed_indicator_series(db_session, count=1, timeframe="5m", start=now - timedelta(minutes=5))

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get(
        "/indicators/readiness",
        params={
            "asset_symbol": "XAG_GRAM",
            "timeframe": "5m",
            "required_min_bar_count": 1,
            "include_policy": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["timeframe_policy"] == {"trend": "1d", "entry": "1h", "execution": "5m"}
    policy_payload = {item["role"]: item for item in payload["policy_readiness"]}
    assert set(policy_payload) == {"trend", "entry", "execution"}
    assert policy_payload["trend"]["timeframe"] == "1d"
    assert policy_payload["trend"]["max_age_minutes"] == 96 * 60
    assert policy_payload["entry"]["timeframe"] == "1h"
    assert policy_payload["entry"]["max_age_minutes"] == 3 * 60
    assert policy_payload["execution"]["timeframe"] == "5m"
    assert policy_payload["execution"]["max_age_minutes"] == 20
    assert all(item["readiness"]["usable"] is True for item in policy_payload.values())
