import json
import os
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


API_BASE_URL = os.getenv("SILVERPILOT_API_BASE_URL", "http://localhost:8000").rstrip("/")


st.set_page_config(page_title="SilverPilot Dashboard", layout="wide")


def fetch_json(path: str, *, timeout_seconds: int = 8) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{API_BASE_URL}{path}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return None, f"{path} returned HTTP {exc.code}"
    except URLError as exc:
        return None, f"{path} request failed: {exc.reason}"
    except TimeoutError:
        return None, f"{path} request timed out"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{path} returned invalid JSON: {exc}"
    if isinstance(payload, dict):
        return payload, None
    return None, f"{path} returned a non-object payload"


def decimal_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def money(value: Any, currency: str = "USD") -> str:
    amount = decimal_value(value)
    if amount is None:
        return "-"
    return f"{amount:,.2f} {currency}"


def number(value: Any, digits: int = 4) -> str:
    amount = decimal_value(value)
    if amount is None:
        return "-"
    return f"{amount:,.{digits}f}"


def percent(value: Any) -> str:
    amount = decimal_value(value)
    if amount is None:
        return "-"
    return f"{amount:,.4f}%"


def age_label(age_seconds: Any) -> str:
    if age_seconds is None:
        return "-"
    try:
        seconds = int(age_seconds)
    except (TypeError, ValueError):
        return "-"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"


def utc_now_label() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def phase4_gate_label(gate: dict[str, Any]) -> str:
    phase4_allowed = gate.get("phase4_allowed")
    if phase4_allowed is True:
        return "allowed"
    if phase4_allowed is False:
        return "blocked"
    return "-"


def active_blocking_reasons(gate: dict[str, Any]) -> list[str]:
    if gate.get("phase4_allowed") is True:
        return []
    return [reason for reason in gate.get("blocking_reasons", []) if reason != "READY"]


@st.cache_data(ttl=20)
def load_dashboard_data(api_base_url: str) -> dict[str, Any]:
    del api_base_url
    endpoints = {
        "health": "/health",
        "portfolio": "/portfolio",
        "position": "/paper-trades/position",
        "latest_price": "/prices/latest",
        "collector_health": "/collectors/health",
        "validation_gate": "/collectors/validation-gate?window_hours=24&expected_interval_minutes=15",
        "risk_status": "/risk/status",
    }
    data: dict[str, Any] = {}
    errors: list[str] = []
    for key, path in endpoints.items():
        payload, error = fetch_json(path)
        data[key] = payload
        if error:
            errors.append(error)
    data["errors"] = errors
    data["loaded_at"] = utc_now_label()
    return data


def metric_card(label: str, value: str, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


def render_status_overview(data: dict[str, Any]) -> None:
    health = data.get("health") or {}
    gate = data.get("validation_gate") or {}
    collector = data.get("collector_health") or {}
    risk = data.get("risk_status") or {}
    would_block_now = risk.get("would_block_now") or []

    cols = st.columns(5)
    with cols[0]:
        metric_card("API", str(health.get("status", "-")))
    with cols[1]:
        metric_card("Database", str(health.get("database", "-")))
    with cols[2]:
        metric_card("Phase 4 gate", phase4_gate_label(gate))
    with cols[3]:
        metric_card("Collectors", str(collector.get("execution_critical_status", "-")))
    with cols[4]:
        metric_card("Would block now", str(len(would_block_now)))

    if health.get("real_money_enabled") is True:
        st.error("REAL_MONEY_ENABLED is true. SilverPilot dashboard is expected to remain paper-only.")
    if data.get("errors"):
        st.warning("Some backend endpoints could not be read.")
        st.code("\n".join(data["errors"]))


def render_portfolio(data: dict[str, Any]) -> None:
    portfolio_payload = data.get("portfolio") or {}
    portfolio = portfolio_payload.get("portfolio") or {}
    snapshot = portfolio.get("latest_snapshot") or {}
    position = data.get("position") or {}
    price = ((data.get("latest_price") or {}).get("price")) or {}

    st.subheader("Portfolio")
    cols = st.columns(5)
    with cols[0]:
        metric_card("Starting balance", money(portfolio.get("initial_cash"), portfolio.get("base_currency", "USD")))
    with cols[1]:
        metric_card("Cash balance", money(portfolio.get("cash_balance"), portfolio.get("base_currency", "USD")))
    with cols[2]:
        metric_card("Net PnL", money(snapshot.get("realized_pnl"), portfolio.get("base_currency", "USD")))
    with cols[3]:
        metric_card("Unrealized PnL", money(snapshot.get("unrealized_pnl"), portfolio.get("base_currency", "USD")))
    with cols[4]:
        metric_card("XAG quantity", number(position.get("asset_quantity"), digits=6))

    st.subheader("Latest Price")
    price_cols = st.columns(5)
    with price_cols[0]:
        metric_card("Source", str(price.get("source", "-")))
    with price_cols[1]:
        metric_card("Buy", money(price.get("buy_price"), price.get("currency", "USD")))
    with price_cols[2]:
        metric_card("Sell", money(price.get("sell_price"), price.get("currency", "USD")))
    with price_cols[3]:
        metric_card("Spread", money(price.get("spread_absolute"), price.get("currency", "USD")))
    with price_cols[4]:
        metric_card("Spread %", percent(price.get("spread_percent")))


def render_risk(data: dict[str, Any]) -> None:
    risk = data.get("risk_status") or {}
    metrics = risk.get("current_metrics") or {}
    recent_decisions = risk.get("recent_decisions") or []
    blocked_count = sum(item.get("count", 0) for item in recent_decisions if item.get("decision") == "blocked")

    st.subheader("Risk Status")
    cols = st.columns(5)
    with cols[0]:
        metric_card("24h XAG volatility", percent(metrics.get("global_xag_volatility_24h_percent")))
        st.caption(
            f"{metrics.get('global_xag_volatility_24h_source') or '-'} / "
            f"{metrics.get('global_xag_volatility_24h_sample_count') or 0} samples"
        )
    with cols[1]:
        metric_card("7d XAG volatility", percent(metrics.get("global_xag_volatility_7d_percent")))
        st.caption(
            f"{metrics.get('global_xag_volatility_7d_source') or '-'} / "
            f"{metrics.get('global_xag_volatility_7d_sample_count') or 0} samples"
        )
    with cols[2]:
        metric_card("FOMO rise", percent(metrics.get("fomo_rise_percent")))
        st.caption(
            f"{metrics.get('fomo_rise_source') or '-'} / "
            f"{metrics.get('fomo_rise_sample_count') or 0} samples"
        )
    with cols[3]:
        metric_card("Daily loss", money(metrics.get("daily_realized_loss_usd")))
    with cols[4]:
        metric_card("Blocked decisions", str(blocked_count))

    would_block_now = risk.get("would_block_now") or []
    if would_block_now:
        st.error("Current market/history diagnostics would block a trade.")
        st.table(would_block_now)
    else:
        st.success("Current market/history diagnostics would not block by themselves.")

    st.subheader("Threshold Headroom")
    headroom_rows = [
        {
            "metric": item.get("metric_name"),
            "status": item.get("status"),
            "value": item.get("metric"),
            "threshold": item.get("threshold"),
            "remaining": item.get("remaining_to_block"),
            "used_percent": item.get("used_percent"),
            "reason_code": item.get("reason_code"),
            "source": item.get("source"),
            "samples": item.get("sample_count"),
        }
        for item in risk.get("threshold_headroom", [])
    ]
    st.table(headroom_rows)

    st.subheader("Recent Decisions")
    decision_rows = [
        {
            "decision": item.get("decision"),
            "reason_code": item.get("reason_code"),
            "count": item.get("count"),
        }
        for item in recent_decisions
    ]
    st.table(decision_rows)


def render_collectors(data: dict[str, Any]) -> None:
    collector = data.get("collector_health") or {}
    gate = data.get("validation_gate") or {}
    execution_critical = collector.get("execution_critical") or {}

    st.subheader("Collectors")
    cols = st.columns(4)
    with cols[0]:
        metric_card("Collector health", str(collector.get("status", "-")))
    with cols[1]:
        metric_card("Execution-critical", str(collector.get("execution_critical_status", "-")))
    with cols[2]:
        metric_card("Selected XAG source", str(gate.get("selected_global_xag_source") or "-"))
    with cols[3]:
        metric_card("Global XAG age", age_label(execution_critical.get("global_xag_age_seconds")))

    freshness_rows = [
        {
            "collector": item.get("collector_name"),
            "source": item.get("source"),
            "status": item.get("status"),
            "age": age_label(item.get("age_seconds")),
            "stale": item.get("stale"),
            "records_seen": item.get("records_seen"),
            "inserted": item.get("records_inserted"),
            "duplicates": item.get("duplicates"),
            "finished_at": item.get("finished_at"),
        }
        for item in collector.get("collectors", [])
    ]
    st.table(freshness_rows)

    blocking_reasons = active_blocking_reasons(gate)
    if blocking_reasons:
        st.error("Validation gate blocking reasons")
        st.write(blocking_reasons)
    if gate.get("degraded_reasons"):
        st.warning("Validation gate degraded reasons")
        st.write(gate.get("degraded_reasons"))


def render_global_xag_samples(data: dict[str, Any]) -> None:
    risk = data.get("risk_status") or {}
    diagnostics = risk.get("global_xag_diagnostics") or []

    st.subheader("Global XAG Samples")
    window_rows = [
        {
            "window_hours": item.get("window_hours"),
            "sample_count": item.get("sample_count"),
            "latest_source": item.get("latest_source"),
            "latest_price": item.get("latest_price"),
            "range_percent": item.get("range_percent"),
            "first_observed_at": item.get("first_observed_at"),
            "last_observed_at": item.get("last_observed_at"),
        }
        for item in diagnostics
    ]
    st.table(window_rows)

    source_rows: list[dict[str, Any]] = []
    for item in diagnostics:
        for source in item.get("sources", []):
            source_rows.append(
                {
                    "window_hours": item.get("window_hours"),
                    "source": source.get("source"),
                    "samples": source.get("sample_count"),
                    "range_percent": source.get("range_percent"),
                    "min_price": source.get("min_price"),
                    "max_price": source.get("max_price"),
                    "first_observed_at": source.get("first_observed_at"),
                    "last_observed_at": source.get("last_observed_at"),
                }
            )
    st.table(source_rows)


st.title("SilverPilot")
st.caption(f"Read-only dashboard from {API_BASE_URL} - loaded {utc_now_label()}")

if st.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

dashboard_data = load_dashboard_data(API_BASE_URL)

render_status_overview(dashboard_data)
render_portfolio(dashboard_data)
render_risk(dashboard_data)
render_collectors(dashboard_data)
render_global_xag_samples(dashboard_data)
