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


def fetch_json(path: str, *, timeout_seconds: int = 8) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    url = f"{API_BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    token = os.getenv("AGENT_API_TOKEN", "")
    if token:
        headers["X-Agent-Token"] = token
    request = Request(url, headers=headers)
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
    if isinstance(payload, (dict, list)):
        return payload, None
    return None, f"{path} returned a non-object payload"


def post_json(path: str, payload: dict[str, Any] | None = None, *, timeout_seconds: int = 20) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    url = f"{API_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    token = os.getenv("AGENT_API_TOKEN", "")
    if token:
        headers["X-Agent-Token"] = token
    
    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
    
    request = Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            res_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8")
            err_json = json.loads(err_body)
            err_msg = err_json.get("detail", err_body)
        except Exception:
            err_msg = f"HTTP {exc.code}"
        return None, f"{path} returned error: {err_msg}"
    except URLError as exc:
        return None, f"{path} request failed: {exc.reason}"
    except TimeoutError:
        return None, f"{path} request timed out"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{path} returned invalid JSON: {exc}"
    if isinstance(res_payload, (dict, list)):
        return res_payload, None
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
        "latest_report": "/reports/daily/latest",
    }
    token = os.getenv("AGENT_API_TOKEN", "")
    if token:
        endpoints["llm_stats"] = "/agent/traces/stats"
        endpoints["llm_traces"] = "/agent/traces?limit=50"
        endpoints["news_memory"] = "/agent/memory?agent_name=news-agent&event_type=news_sentiment&limit=5"
        endpoints["risk_memory"] = "/agent/memory?agent_name=risk-agent&event_type=signal_critique&limit=5"
        
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


def render_llm_observability(data: dict[str, Any]) -> None:
    st.subheader("LLM Analytics & Observability")
    
    llm_stats = data.get("llm_stats") or {}
    llm_traces = data.get("llm_traces") or []
    
    # 1. High level metrics
    cols = st.columns(4)
    with cols[0]:
        metric_card(
            "Total LLM Spend", 
            f"${llm_stats.get('total_cost_usd', 0.0):,.6f}",
            help_text="Accumulated cost of all LLM calls made by agents."
        )
    with cols[1]:
        metric_card(
            "Total LLM Calls", 
            f"{llm_stats.get('total_calls', 0):,}",
            help_text="Total number of API executions to DeepSeek."
        )
    with cols[2]:
        avg_lat = llm_stats.get('avg_latency_ms', 0.0)
        metric_card(
            "Avg Response Latency", 
            f"{avg_lat:,.0f} ms" if avg_lat else "-",
            help_text="Average response latency in milliseconds."
        )
    with cols[3]:
        st.metric("Status", "Active", help="Budget guard active and monitoring")
        
    # 2. Breakdowns using neat columns
    st.markdown("---")
    col_agent, col_model = st.columns(2)
    
    with col_agent:
        st.markdown("#### Cost by Agent")
        by_agent = llm_stats.get("by_agent") or []
        if by_agent:
            agent_rows = [
                {
                    "Agent Name": item.get("agent_name"),
                    "Calls Count": f"{item.get('calls'):,}",
                    "Total Cost": f"${item.get('total_cost_usd', 0.0):,.6f}",
                    "Avg Latency": f"{item.get('avg_latency_ms', 0.0):,.0f} ms"
                }
                for item in by_agent
            ]
            st.table(agent_rows)
        else:
            st.info("No agent telemetry recorded yet.")
            
    with col_model:
        st.markdown("#### Cost by Model")
        by_model = llm_stats.get("by_model") or []
        if by_model:
            model_rows = [
                {
                    "Model Name": item.get("model_name"),
                    "Calls Count": f"{item.get('calls'):,}",
                    "Total Cost": f"${item.get('total_cost_usd', 0.0):,.6f}",
                    "Avg Latency": f"{item.get('avg_latency_ms', 0.0):,.0f} ms"
                }
                for item in by_model
            ]
            st.table(model_rows)
        else:
            st.info("No model telemetry recorded yet.")
            
    # 3. Recent Call Logs
    st.markdown("---")
    st.markdown("#### Recent 50 LLM Call Logs")
    if llm_traces:
        log_rows = []
        for i, item in enumerate(llm_traces):
            created_dt = item.get("created_at")
            if created_dt:
                try:
                    dt = datetime.fromisoformat(created_dt.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    time_str = created_dt
            else:
                time_str = "-"
                
            log_rows.append({
                "Index": i + 1,
                "Time": time_str,
                "Agent": item.get("agent_name"),
                "Model": item.get("model_name"),
                "Status": item.get("status"),
                "Cost": f"${float(item.get('total_cost_usd', 0)):,.6f}",
                "Latency": f"{item.get('latency_ms', 0):,} ms",
                "Tokens (In/Out)": f"{item.get('prompt_tokens', 0)} / {item.get('completion_tokens', 0)}"
            })
            
        st.dataframe(log_rows, use_container_width=True)
        
        # Interactive raw inspector
        st.markdown("##### Inspect Raw Trace Content")
        trace_indices = [f"{r['Index']}. [{r['Agent']}] {r['Model']} ({r['Time']})" for r in log_rows]
        selected_option = st.selectbox("Select a trace to view full prompt and response details:", trace_indices)
        if selected_option:
            sel_idx = int(selected_option.split(".")[0]) - 1
            sel_trace = llm_traces[sel_idx]
            
            p_col, r_col = st.columns(2)
            with p_col:
                st.markdown("**Prompt Raw:**")
                st.code(sel_trace.get("prompt_raw") or "Empty prompt")
            with r_col:
                if sel_trace.get("status") == "SUCCESS":
                    st.markdown("**Response Raw:**")
                    st.code(sel_trace.get("response_raw") or "Empty response")
                else:
                    st.markdown("**Error Message:**")
                    st.error(sel_trace.get("error_message") or "Unknown error")
    else:
        st.info("No LLM calls recorded in the database yet.")


def render_active_agents(data: dict[str, Any]) -> None:
    st.subheader("Active Financial Agents Panel")
    st.caption("Trigger active reasoning loops and view persisted news sentiments, risk critiques, and daily performance reports.")

    token = os.getenv("AGENT_API_TOKEN", "")
    if not token:
        st.warning("⚠️ AGENT_API_TOKEN is not configured. Triggering agents and viewing memory events are disabled for security.")
        return

    sub_tab_news, sub_tab_risk, sub_tab_report = st.tabs([
        "📰 News Sentiment Agent",
        "🛡️ Risk Auditor Agent",
        "📊 Daily Performance Report Agent"
    ])

    # 1. NEWS SENTIMENT AGENT SUB-TAB
    with sub_tab_news:
        st.markdown("### 📰 News Sentiment Analysis")
        st.markdown(
            "Synthesizes raw financial news from the last 24 hours, determines overall market sentiment for Silver (XAG), "
            "and generates structured summaries using **DeepSeek V4 Flash**."
        )
        
        # Display latest sentiment
        news_memory = data.get("news_memory")
        latest_news = news_memory[0] if news_memory else None
        
        col_act, col_info = st.columns([1, 3])
        with col_act:
            if st.button("Trigger News Sentiment Analysis", key="trigger_news_btn"):
                with st.spinner("Analyzing market news..."):
                    payload, err = post_json("/agent/news/trigger")
                    if err:
                        st.error(f"Failed to trigger: {err}")
                    else:
                        st.success("News analysis completed successfully!")
                        st.cache_data.clear()
                        st.rerun()
        with col_info:
            if latest_news:
                val = latest_news.get("value_json") or {}
                analyzed_at = val.get("analyzed_at", latest_news.get("created_at", "-"))
                st.caption(f"Last executed: **{analyzed_at}**")
            else:
                st.caption("No sentiment analysis recorded yet.")

        st.markdown("---")

        if latest_news:
            val = latest_news.get("value_json") or {}
            sentiment = val.get("sentiment", "NEUTRAL")
            confidence = val.get("confidence", 0.0)
            summary = val.get("summary_markdown", "")
            
            # Sentiment metrics card with premium aesthetics
            c1, c2 = st.columns([1, 2])
            with c1:
                if sentiment == "BULLISH":
                    st.success(f"📈 **BULLISH**\n\nConfidence: {confidence:.1%}")
                elif sentiment == "BEARISH":
                    st.error(f"📉 **BEARISH**\n\nConfidence: {confidence:.1%}")
                else:
                    st.warning(f"➡️ **NEUTRAL**\n\nConfidence: {confidence:.1%}")
            with c2:
                st.info("💡 **Agent Insight Summary**")
                st.markdown(summary or "No summary content available.")

            if len(news_memory) > 1:
                with st.expander("Show Sentiment Analysis History"):
                    for hist in news_memory[1:]:
                        h_val = hist.get("value_json") or {}
                        h_sent = h_val.get("sentiment", "NEUTRAL")
                        h_conf = h_val.get("confidence", 0.0)
                        h_dt = h_val.get("analyzed_at", hist.get("created_at", ""))
                        st.markdown(f"**{h_dt[:16]}** - `{h_sent}` (Conf: {h_conf:.1%})")
                        st.markdown(h_val.get("summary_markdown", ""))
                        st.markdown("---")
        else:
            st.info("Click the button above to run the News Sentiment Analysis for the first time.")

    # 2. RISK AUDITOR AGENT SUB-TAB
    with sub_tab_risk:
        st.markdown("### 🛡️ Strategy Signal Critique")
        st.markdown(
            "Audits trading signals using high-reasoning **DeepSeek V4 Pro** models to critique "
            "decisions against current technical indicators and portfolio exposure."
        )

        col_in, col_btn = st.columns([2, 1])
        with col_in:
            signal_id_str = st.text_input("Signal ID (Leave empty to audit the latest signal)", key="risk_sig_input")
        with col_btn:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Trigger Signal Critique", key="trigger_risk_btn"):
                payload = {}
                if signal_id_str.strip().isdigit():
                    payload["signal_id"] = int(signal_id_str.strip())
                with st.spinner("Auditing trade signal..."):
                    res, err = post_json("/agent/risk/critique", payload)
                    if err:
                        st.error(f"Failed to critique signal: {err}")
                    else:
                        st.success("Risk critique completed successfully!")
                        st.cache_data.clear()
                        st.rerun()

        st.markdown("---")

        risk_memory = data.get("risk_memory")
        latest_risk = risk_memory[0] if risk_memory else None

        if latest_risk:
            val = latest_risk.get("value_json") or {}
            decision = val.get("decision", "APPROVED")
            confidence = val.get("confidence", 0.0)
            critique = val.get("critique_markdown", "")
            sig_id = val.get("signal_id", "-")
            analyzed_at = val.get("analyzed_at", latest_risk.get("created_at", "-"))

            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"**Signal Audited:** #{sig_id}")
                st.caption(f"Audited at: {analyzed_at[:19]}")
                if decision == "APPROVED":
                    st.success(f"✅ **APPROVED**\n\nConfidence: {confidence:.1%}")
                elif decision == "CAUTION":
                    st.warning(f"⚠️ **CAUTION**\n\nConfidence: {confidence:.1%}")
                else:
                    st.error(f"❌ **REJECTED**\n\nConfidence: {confidence:.1%}")
            with c2:
                st.info("🛡️ **Critique & Risk Audit Notes**")
                st.markdown(critique or "No critique details available.")

            if len(risk_memory) > 1:
                with st.expander("Show Critique History"):
                    for hist in risk_memory[1:]:
                        h_val = hist.get("value_json") or {}
                        h_dec = h_val.get("decision", "APPROVED")
                        h_conf = h_val.get("confidence", 0.0)
                        h_sig = h_val.get("signal_id", "-")
                        h_dt = h_val.get("analyzed_at", hist.get("created_at", ""))
                        st.markdown(f"**Signal #{h_sig} Audited at {h_dt[:16]}** - `{h_dec}` (Conf: {h_conf:.1%})")
                        st.markdown(h_val.get("critique_markdown", ""))
                        st.markdown("---")
        else:
            st.info("No risk critique reports found in memory. Trigger a critique to view results.")

    # 3. REPORT AGENT SUB-TAB
    with sub_tab_report:
        st.markdown("### 📊 Daily Performance Report")
        st.markdown(
            "Synthesizes portfolio balances and transaction history over the last 24 hours to generate a "
            "comprehensive report detailing daily stats, PnL, and precious metal commentary using **DeepSeek V4 Flash**."
        )

        col_rpt_btn, col_rpt_info = st.columns([1, 3])
        with col_rpt_btn:
            if st.button("Generate Daily Performance Report", key="trigger_rpt_btn"):
                with st.spinner("Compiling and generating daily report..."):
                    res, err = post_json("/agent/report/trigger")
                    if err:
                        st.error(f"Failed to generate report: {err}")
                    else:
                        st.success("Report generated successfully!")
                        st.cache_data.clear()
                        st.rerun()
        with col_rpt_info:
            report_envelope = data.get("latest_report")
            report = report_envelope.get("report") if report_envelope else None
            if report:
                created_at = report.get("created_at", "-")
                st.caption(f"Latest report generated at: **{created_at}**")
            else:
                st.caption("No reports compiled yet.")

        st.markdown("---")

        if report:
            payload = report.get("payload") or report.get("payload_json") or {}
            port_val = payload.get("portfolio_value", 0.0)
            cash_bal = payload.get("cash_balance", 0.0)
            trades_count = payload.get("trades_count", 0)
            report_markdown = payload.get("report_content", "")

            # Show report overview metrics
            m1, m2, m3 = st.columns(3)
            with m1:
                metric_card("Report Portfolio Value", money(port_val))
            with m2:
                metric_card("Report Cash Balance", money(cash_bal))
            with m3:
                metric_card("24h Trades In Report", f"{trades_count}")

            st.markdown("#### Performance Summary Report")
            st.markdown(report_markdown or "No report content found.")
        else:
            st.info("Click the button above to synthesize and compile a daily performance report.")


st.title("SilverPilot")
st.caption(f"Read-only dashboard from {API_BASE_URL} - loaded {utc_now_label()}")

if st.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

dashboard_data = load_dashboard_data(API_BASE_URL)

# Premium Tabs Interface
tab_portfolio, tab_risk, tab_collectors, tab_samples, tab_observability, tab_active_agents = st.tabs([
    "💼 Portfolio & Overview",
    "🛡️ Risk Diagnostics",
    "🔌 Collectors Health",
    "📊 Global XAG Samples",
    "👁️ LLM Observability",
    "🤖 Active Financial Agents"
])

with tab_portfolio:
    render_status_overview(dashboard_data)
    render_portfolio(dashboard_data)

with tab_risk:
    render_risk(dashboard_data)

with tab_collectors:
    render_collectors(dashboard_data)

with tab_samples:
    render_global_xag_samples(dashboard_data)

with tab_observability:
    render_llm_observability(dashboard_data)

with tab_active_agents:
    render_active_agents(dashboard_data)
