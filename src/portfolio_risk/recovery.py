"""Recovery of the window's maximum drawdown, counted in official market sessions.

Rules (recovery policy ``1.1-window-bound-session-count``):

* The event is the maximum drawdown of the selected window, measured on the TWR wealth
  path including the opening point.
* Recovery is the first point after the trough at or above the reference peak.
* The search stops at the window end, inclusive. A recovery that happens after the
  window does not change that window's answer: it stays "not recovered by the end of
  this period". Adding new data later cannot rewrite a past window.
* Duration = number of official sessions in ``(trough_date, recovery_date]``: the trough
  session is not counted, the recovery session is. Holidays do not count. A session on
  which the market was open but the investor did not trade does count.
* Duration comes from the official calendar, never from the number of rows the
  investor happens to have.
* "Not recovered" and "no drawdown" have no numeric duration. Neither is zero.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .metrics import max_drawdown, wealth_index


def count_sessions(trough: date, recovery: date, official_sessions: Sequence[date]) -> int:
    """Official sessions in (trough, recovery]. ``official_sessions`` must be sorted and unique."""
    if list(official_sessions) != sorted(set(official_sessions)):
        raise ValueError("OFFICIAL_CALENDAR_MUST_BE_SORTED_AND_UNIQUE")
    if recovery <= trough:
        raise ValueError("INVALID_RECOVERY_ENDPOINTS")
    if recovery not in official_sessions:
        raise ValueError("RECOVERY_DATE_IS_NOT_A_SESSION")
    lo = bisect.bisect_right(official_sessions, trough)
    hi = bisect.bisect_right(official_sessions, recovery)
    return hi - lo


@dataclass(frozen=True)
class RecoveryOutcome:
    state: str                    # "recovered" | "not_recovered" | "no_drawdown"
    drawdown: float
    peak_date: date | None
    trough_date: date | None
    recovery_date: date | None
    sessions: int | None
    tied: bool


def find_recovery(
    point_dates: Sequence[date],
    returns: Sequence[float],
    official_sessions: Sequence[date],
    tie_rule: str = "earliest",
    rel_tol: float = 1e-12,
) -> RecoveryOutcome:
    """Locate the maximum-drawdown event of a window and its recovery inside the window.

    ``point_dates[0]`` is the opening boundary (the wealth point before the first return);
    ``point_dates[i]`` is the session of return ``i``. Data after the window must simply
    not be passed in; that is how the window bound is enforced.
    """
    if len(point_dates) != len(returns) + 1:
        raise ValueError("point_dates must have one more entry than returns (the opening point)")
    event = max_drawdown(returns, tie_rule=tie_rule)
    if event.value == 0.0:
        return RecoveryOutcome("no_drawdown", 0.0, None, None, None, None, False)
    wealth = wealth_index(returns)
    peak_level = wealth[event.peak_index]
    trough_date = point_dates[event.trough_index]
    for j in range(event.trough_index + 1, len(wealth)):
        if wealth[j] >= peak_level * (1 - rel_tol):
            recovery_date = point_dates[j]
            n = count_sessions(trough_date, recovery_date, official_sessions)
            return RecoveryOutcome("recovered", event.value, point_dates[event.peak_index], trough_date,
                                   recovery_date, n, event.tied)
    return RecoveryOutcome("not_recovered", event.value, point_dates[event.peak_index], trough_date,
                           None, None, event.tied)
