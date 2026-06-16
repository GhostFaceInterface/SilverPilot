from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.risk.service import is_comex_market_closed

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class TimeframeFreshness:
    timeframe: str
    market_state: str
    expected_next_bar_at: datetime | None
    freshness_status: str
    reason_code: str | None

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "market_state": self.market_state,
            "expected_next_bar_at": self.expected_next_bar_at,
            "freshness_status": self.freshness_status,
            "reason_code": self.reason_code,
        }


def comex_timeframe_freshness(
    *,
    timeframe: str,
    latest_bar_at: datetime | None,
    max_age_minutes: int,
    now: datetime | None = None,
) -> TimeframeFreshness:
    now = _aware(now or datetime.now(UTC))
    latest = _aware(latest_bar_at) if latest_bar_at is not None else None
    market_closed = is_comex_market_closed(now)
    market_state = "closed" if market_closed else "open"

    if timeframe == "1d":
        expected = previous_completed_comex_daily_bar_at(now)
        if latest is not None and latest >= expected:
            return TimeframeFreshness(timeframe, market_state, expected, "fresh", None)
        grace_cutoff = expected + timedelta(minutes=max_age_minutes)
        if now <= grace_cutoff:
            return TimeframeFreshness(timeframe, market_state, expected, "pending", None)
        return TimeframeFreshness(timeframe, market_state, expected, "delayed", "DAILY_BAR_DELAYED")

    if market_closed:
        expected = next_intraday_bar_at(now, timeframe)
        return TimeframeFreshness(timeframe, market_state, expected, "market_closed", "MARKET_CLOSED")

    expected = next_intraday_bar_at(now, timeframe)
    if latest is None:
        reason = "EXECUTION_TIMEFRAME_STALE" if timeframe == "5m" else "ENTRY_TIMEFRAME_STALE"
        return TimeframeFreshness(timeframe, market_state, expected, "stale", reason)

    age_seconds = int((now - latest).total_seconds())
    if age_seconds > max_age_minutes * 60:
        reason = "EXECUTION_TIMEFRAME_STALE" if timeframe == "5m" else "ENTRY_TIMEFRAME_STALE"
        return TimeframeFreshness(timeframe, market_state, expected, "stale", reason)
    return TimeframeFreshness(timeframe, market_state, expected, "fresh", None)


def previous_completed_comex_daily_bar_at(now: datetime) -> datetime:
    et_now = _aware(now).astimezone(ET)
    close_today = datetime.combine(et_now.date(), time(17, 0), tzinfo=ET)
    candidate = close_today if et_now >= close_today else close_today - timedelta(days=1)
    while is_comex_market_closed(candidate - timedelta(minutes=1)):
        candidate -= timedelta(days=1)
    return candidate.astimezone(UTC)


def next_intraday_bar_at(now: datetime, timeframe: str) -> datetime | None:
    minutes = {"5m": 5, "1h": 60}.get(timeframe)
    if minutes is None:
        return None
    et_now = _aware(now).astimezone(ET)
    if is_comex_market_closed(et_now):
        reopen = _next_comex_reopen(et_now)
        return reopen.astimezone(UTC)
    minute_bucket = (et_now.minute // minutes + 1) * minutes
    if minute_bucket >= 60:
        next_et = et_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_et = et_now.replace(minute=minute_bucket, second=0, microsecond=0)
    if is_comex_market_closed(next_et):
        next_et = _next_comex_reopen(next_et)
    return next_et.astimezone(UTC)


def _next_comex_reopen(et_dt: datetime) -> datetime:
    current = et_dt if et_dt.tzinfo is not None else et_dt.replace(tzinfo=ET)
    for _ in range(8 * 24):
        if not is_comex_market_closed(current) and is_comex_market_closed(current - timedelta(minutes=1)):
            return current.replace(second=0, microsecond=0)
        current += timedelta(minutes=30)
    return current.replace(second=0, microsecond=0)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
