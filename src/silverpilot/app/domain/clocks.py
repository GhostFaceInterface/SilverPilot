from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""


class RealClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    def __init__(self, initial_time: datetime) -> None:
        self._current_time = _require_aware_utc(initial_time)

    def now(self) -> datetime:
        return self._current_time

    def set(self, current_time: datetime) -> None:
        self._current_time = _require_aware_utc(current_time)


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


ClockFactory = Callable[[], Clock]
