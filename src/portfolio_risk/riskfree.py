"""Risk-free returns from Treasury-bill yield quotes.

The market quotes the risk-free rate as an *annual yield to maturity* (YTM) of government
Treasury bills (in Iran, Islamic Treasury Bills). Sharpe, Sortino and downside deviation
need a risk-free *return per session*, aligned with each daily portfolio return.

Convention (methodology 1.2 onwards)::

    rf_t = (1 + YTM_t) ** (1 / 250) - 1        one value per official market session

* 250 is the fixed number of trading periods per year, the same factor used to
  annualise volatility. It is not the number of calendar days.
* A Saturday return that follows a two-day closure still receives one session of
  risk-free return, not three days of calendar accrual (an earlier ACT/365 draft did that).
* Each session uses the quote of that same session. A missing quote is never filled with
  zero, with yesterday's quote, or with today's rate.
* A weekly risk-free return compounds the *daily* values over the week's sessions; it is
  not ``(1 + YTM) ** (1 / 52) - 1``.
"""

from __future__ import annotations

import math
from typing import Iterable

PERIODS_PER_YEAR = 250


class RiskFreeError(ValueError):
    """Raised for an unusable quote; ``reason`` is a machine-readable code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def normalise_ytm(value: float, unit: str) -> float:
    """Convert a quote to a decimal annual yield (0.30 = 30%).

    The unit must be declared. It cannot be guessed from the size of the number:
    1.0 may be a 1% quote or a 100% yield.
    """
    if unit not in ("decimal", "percent"):
        raise RiskFreeError("RF_UNIT_UNKNOWN", f"unit {unit!r}")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RiskFreeError("INVALID_RF_QUOTE", f"value {value!r}")
    ytm = value / 100.0 if unit == "percent" else float(value)
    if ytm <= -1.0:
        raise RiskFreeError("INVALID_RF_QUOTE", f"yield {ytm!r} is not above -100%")
    return ytm


def session_rf(annual_ytm: float, sessions: int = 1, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Risk-free return over ``sessions`` official market sessions.

    ``expm1``/``log1p`` keep full precision for small daily values.
    """
    if isinstance(annual_ytm, bool) or not math.isfinite(annual_ytm) or annual_ytm <= -1:
        raise RiskFreeError("INVALID_RF_QUOTE", f"yield {annual_ytm!r}")
    if isinstance(sessions, bool) or int(sessions) != sessions or sessions <= 0:
        raise RiskFreeError("INVALID_SESSION_COUNT", f"sessions {sessions!r}")
    return math.expm1(math.log1p(annual_ytm) * sessions / periods_per_year)


def compound(returns: Iterable[float]) -> float:
    """Geometric linking: ``prod(1 + x) - 1``."""
    return math.prod(1.0 + x for x in returns) - 1.0
