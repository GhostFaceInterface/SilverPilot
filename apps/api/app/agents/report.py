import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.gateway import DeepSeekGateway
from app.models import PortfolioSnapshot, PaperTrade, Report

logger = logging.getLogger("silverpilot.agents.report")


async def run_daily_performance_report(db: Session) -> Report:
    """
    Query the latest portfolio snapshot and last 24h trading activity,
    call DeepSeek LLM (deepseek-v4-flash) to generate a professional performance report,
    persist it to the reports table, and return the report.
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=24)
    period_end = now

    # 1. Query the latest PortfolioSnapshot
    stmt_snapshot = (
        select(PortfolioSnapshot)
        .order_by(desc(PortfolioSnapshot.observed_at))
        .limit(1)
    )
    portfolio_snapshot = db.execute(stmt_snapshot).scalar_one_or_none()

    # 2. Query all PaperTrade records in the 24-hour window
    stmt_trades = (
        select(PaperTrade)
        .where(PaperTrade.created_at >= period_start)
        .where(PaperTrade.created_at <= period_end)
        .order_by(desc(PaperTrade.created_at))
    )
    trades = db.execute(stmt_trades).scalars().all()

    # 3. Graceful fallback if database is empty (no portfolio snapshot exists)
    if portfolio_snapshot is None:
        logger.info("No portfolio snapshot exists in the database. Gracefully bypassing LLM calling.")
        markdown_string = (
            "# Daily Performance Report (Fallback)\n\n"
            "No active portfolio data or snapshots found in the database. Generating default empty report.\n\n"
            "## Portfolio Highlights\n"
            "- **Total Portfolio Value:** $0.00 USD\n"
            "- **Cash Balance:** $0.00 USD\n"
            "- **Asset Quantity:** 0.000000 XAG (Silver)\n"
            "- **Realized PnL:** $0.00 USD\n"
            "- **Unrealized PnL:** $0.00 USD\n\n"
            "## Trading Activity (Last 24 Hours)\n"
            "- **Total Trades:** 0\n\n"
            "## Strategic Outlook\n"
            "System is waiting for price feed collectors and strategy execution to begin."
        )

        report = Report(
            report_type="daily",
            period_start=period_start,
            period_end=period_end,
            payload_json={
                "report_content": markdown_string,
                "portfolio_value": 0.0,
                "cash_balance": 0.0,
                "trades_count": 0,
            },
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    # 4. Format collected metrics and trades
    portfolio_value = portfolio_snapshot.portfolio_value
    cash_balance = portfolio_snapshot.cash_balance
    asset_quantity = portfolio_snapshot.asset_quantity
    realized_pnl = portfolio_snapshot.realized_pnl
    unrealized_pnl = portfolio_snapshot.unrealized_pnl

    trades_lines = []
    for t in trades:
        trades_lines.append(
            f"- Action: {t.action} | Quantity: {float(t.quantity):.6f} | "
            f"Price: ${float(t.price):.2f} USD | Net Amount: ${float(t.net_amount):.2f} USD | "
            f"Created At: {t.created_at.isoformat()}"
        )
    formatted_trades = "\n".join(trades_lines) if trades_lines else "No trades executed."

    # 5. Construct prompts and invoke DeepSeek
    settings = get_settings()
    model = settings.agent_report_model or "deepseek-v4-flash"

    system_prompt = (
        "You are an expert precious metals financial analyst and automated reporter for the SilverPilot trading platform.\n"
        "Your task is to generate a beautifully styled, professional markdown performance report summarizing the last 24 hours of trading activity, portfolio highlights, and market comments.\n"
        "You must return ONLY the raw markdown string directly. Do NOT wrap it in any JSON, markdown code blocks (like ```markdown), or additional text explanations."
    )

    user_prompt = (
        f"Please generate a 24-hour performance report based on the following trading and portfolio data:\n\n"
        f"Time Period: {period_start.isoformat()} to {period_end.isoformat()}\n\n"
        f"Portfolio Metrics:\n"
        f"- Total Portfolio Value: ${float(portfolio_value):.2f} USD\n"
        f"- Cash Balance: ${float(cash_balance):.2f} USD\n"
        f"- Asset Quantity: {float(asset_quantity):.6f} XAG (Silver)\n"
        f"- Realized PnL: ${float(realized_pnl):.2f} USD\n"
        f"- Unrealized PnL: ${float(unrealized_pnl):.2f} USD\n\n"
        f"Trading Activity (Last 24 Hours):\n"
        f"- Number of Trades: {len(trades)}\n"
        f"Trades List:\n{formatted_trades}\n\n"
        f"Provide a structured report with these sections:\n"
        f"1. Executive Summary\n"
        f"2. Portfolio Valuation & Performance Highlights\n"
        f"3. Trading Activity & Execution Details\n"
        f"4. Market Comments & Strategic Outlook\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"Calling Report Agent LLM using model: {model} with {len(trades)} trades.")
    response = await DeepSeekGateway.generate_completion(
        db=db,
        agent_name="report-agent",
        model=model,
        messages=messages,
        temperature=0.3,
    )

    markdown_string = response.get("content", "").strip()

    # Clean markdown block wrapping if LLM included them
    if markdown_string.startswith("```"):
        lines = markdown_string.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        markdown_string = "\n".join(lines).strip()

    # 6. Save the generated report
    report = Report(
        report_type="daily",
        period_start=period_start,
        period_end=period_end,
        payload_json={
            "report_content": markdown_string,
            "portfolio_value": float(portfolio_value),
            "cash_balance": float(cash_balance),
            "trades_count": len(trades),
        },
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(f"Report agent run completed and saved successfully. Report ID: {report.id}")
    return report
