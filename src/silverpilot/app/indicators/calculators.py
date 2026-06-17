from collections.abc import Sequence
from decimal import Decimal, getcontext
from typing import Protocol

getcontext().prec = 28


class IndicatorInsufficientData(ValueError):
    """Raised when an indicator warmup window is not satisfied."""


class BarLike(Protocol):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def calculate_ema(bars: Sequence[BarLike], *, period: int) -> Decimal:
    _validate_period(period)
    if len(bars) < period:
        raise IndicatorInsufficientData("EMA requires at least period bars")

    closes = [bar.close for bar in bars]
    ema = sum(closes[:period], Decimal("0")) / Decimal(period)
    multiplier = Decimal("2") / Decimal(period + 1)
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


def calculate_rsi(bars: Sequence[BarLike], *, period: int) -> Decimal:
    _validate_period(period)
    if len(bars) < period + 1:
        raise IndicatorInsufficientData("RSI requires at least period + 1 bars")

    closes = [bar.close for bar in bars]
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    positive = [max(change, Decimal("0")) for change in changes]
    negative = [min(change, Decimal("0")) for change in changes]
    avg_gain = _rma(positive, period)[-1]
    avg_loss = _rma(negative, period)[-1]

    if avg_loss == 0 and avg_gain > 0:
        return Decimal("100")
    if avg_gain == 0 and avg_loss == 0:
        return Decimal("0")
    return Decimal("100") * avg_gain / (avg_gain + abs(avg_loss))


def calculate_atr(bars: Sequence[BarLike], *, period: int) -> Decimal:
    _validate_period(period)
    if len(bars) < period + 1:
        raise IndicatorInsufficientData("ATR requires at least period + 1 bars")

    true_ranges = _true_ranges_with_first_bar(bars)
    presmoothed: list[Decimal | None] = [None] * (period - 1)
    presmoothed.append(sum(true_ranges[:period], Decimal("0")) / Decimal(period))
    presmoothed.extend(true_ranges[period:])
    atr = _rma_optional(presmoothed, period)[-1]
    assert atr is not None
    return atr


def calculate_adx(bars: Sequence[BarLike], *, period: int) -> Decimal:
    _validate_period(period)
    if len(bars) < period * 2:
        raise IndicatorInsufficientData("ADX requires at least period * 2 bars")

    plus_dm: list[Decimal] = []
    minus_dm: list[Decimal] = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]

        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else Decimal("0"))
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else Decimal("0"))

    atr_values = _atr_series(bars, period)
    plus_rma = _rma_optional([None, *plus_dm], period)
    minus_rma = _rma_optional([None, *minus_dm], period)
    dx_values: list[Decimal | None] = []
    for atr_value, plus_value, minus_value in zip(
        atr_values,
        plus_rma,
        minus_rma,
        strict=True,
    ):
        if atr_value is None or plus_value is None or minus_value is None or atr_value == 0:
            dx_values.append(None)
            continue
        plus_di = Decimal("100") * plus_value / atr_value
        minus_di = Decimal("100") * minus_value / atr_value
        if plus_di + minus_di == 0:
            dx_values.append(Decimal("0"))
            continue
        dx_values.append(Decimal("100") * (abs(plus_di - minus_di) / (plus_di + minus_di)))

    adx = _rma_optional(dx_values, period)[-1]
    assert adx is not None
    return adx


def calculate_bollinger_band_width(
    bars: Sequence[BarLike],
    *,
    period: int,
    standard_deviations: Decimal = Decimal("2"),
    ddof: int = 1,
) -> Decimal:
    _validate_period(period)
    if standard_deviations <= 0:
        raise ValueError("standard_deviations must be greater than zero")
    if len(bars) < period:
        raise IndicatorInsufficientData("Bollinger Band Width requires at least period bars")
    if ddof < 0 or ddof >= period:
        raise ValueError("ddof must be non-negative and less than period")

    closes = [bar.close for bar in bars[-period:]]
    mean = sum(closes, Decimal("0")) / Decimal(period)
    if mean == 0:
        raise ValueError("Bollinger Band Width is undefined when moving average is zero")

    variance = sum(((close - mean) ** 2 for close in closes), Decimal("0")) / Decimal(period - ddof)
    standard_deviation = variance.sqrt()
    upper = mean + (standard_deviation * standard_deviations)
    lower = mean - (standard_deviation * standard_deviations)
    return Decimal("100") * (upper - lower) / mean


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be greater than zero")


def _true_ranges(bars: Sequence[BarLike]) -> list[Decimal]:
    return [_true_range(bars[index], bars[index - 1].close) for index in range(1, len(bars))]


def _true_ranges_with_first_bar(bars: Sequence[BarLike]) -> list[Decimal]:
    return [bars[0].high - bars[0].low, *_true_ranges(bars)]


def _true_range(bar: BarLike, previous_close: Decimal) -> Decimal:
    return max(
        bar.high - bar.low,
        abs(bar.high - previous_close),
        abs(bar.low - previous_close),
    )


def _atr_series(bars: Sequence[BarLike], period: int) -> list[Decimal | None]:
    true_ranges = _true_ranges(bars)
    presmoothed: list[Decimal | None] = [None] * period
    presmoothed[period - 1] = sum(true_ranges[: period - 1], Decimal("0")) / Decimal(period - 1)
    presmoothed.extend(true_ranges[period - 1 :])
    return _rma_optional(presmoothed, period)


def _rma(values: Sequence[Decimal], period: int) -> list[Decimal]:
    return [value for value in _rma_optional(values, period) if value is not None]


def _rma_optional(values: Sequence[Decimal | None], period: int) -> list[Decimal | None]:
    alpha = Decimal("1") / Decimal(period)
    average: Decimal | None = None
    smoothed: list[Decimal | None] = []
    for value in values:
        if value is None:
            smoothed.append(None)
            continue
        average = value if average is None else alpha * value + (Decimal("1") - alpha) * average
        smoothed.append(average)
    return smoothed
