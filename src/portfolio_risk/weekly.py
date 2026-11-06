"""Sharpe and Sortino from weekly observations, alongside the unchanged daily ratios.

Approved formulas (weekly policy ``weekly-ratios-v1``)::

    R_w = prod(1 + r_t) - 1          portfolio, over the week's valid sessions
    F_w = prod(1 + rf_t) - 1         risk-free, over exactly the same sessions
    x_w = R_w - F_w                  (daily excess returns are NOT compounded)
    Sharpe_w  = mean(x_w) / sample_sd(x_w) * sqrt(52)
    Sortino_w = mean(x_w) / sqrt(sum(min(x_w, 0)^2) / N) * sqrt(52)

The daily risk-free conversion stays ``(1 + YTM) ** (1/250) - 1``; the weekly value is
built by compounding those daily values, never by ``(1 + YTM) ** (1/52) - 1``.

What was *not* approved: the official week boundary, what to do with partial weeks at
the window edges, and minimum numbers of weeks and weekly shortfalls. 52 is a scaling
factor, not a minimum history. Until those decisions exist, weekly ratios are computed as
diagnostics and published as ``POLICY_PENDING``. This module uses a Monday-to-Sunday
week as an example plan, excludes
partial weeks from the diagnostic and reports them; it never pads a closed week with a
zero observation.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from .metrics import Undefined, downside_deviation, sharpe, sortino
from .riskfree import compound

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


@dataclass(frozen=True)
class Week:
    start: date                     # first calendar day of the week
    sessions: tuple[date, ...]      # official sessions of this week inside the window
    complete: bool                  # every official session of the calendar week is inside the window


def week_start_of(d: date, week_start: str = "monday") -> date:
    return d - timedelta(days=(d.weekday() - WEEKDAYS[week_start]) % 7)


def plan_weeks(window_sessions: Sequence[date], all_sessions: Sequence[date], opening: date, end: date,
               week_start: str = "monday") -> list[Week]:
    """Group the window's sessions into calendar weeks and mark edge weeks as partial."""
    groups: "OrderedDict[date, list[date]]" = OrderedDict()
    for s in window_sessions:
        groups.setdefault(week_start_of(s, week_start), []).append(s)
    weeks = []
    for start, inside in groups.items():
        week_end = start + timedelta(days=6)
        official = [s for s in all_sessions if start <= s <= week_end]
        complete = all(opening < s <= end for s in official)
        weeks.append(Week(start, tuple(inside), complete))
    return weeks


@dataclass(frozen=True)
class WeeklySeries:
    weeks: list[date]
    portfolio: list[float]
    rf: list[float]
    partial_weeks: list[date]
    empty_weeks: list[date]          # weeks whose sessions were all not_computed


def aggregate_weekly(obs_dates: Sequence[date], returns: Sequence[float], rf: Sequence[float],
                     weeks: Sequence[Week]) -> WeeklySeries:
    """Compound portfolio and risk-free returns separately over identical sessions."""
    if any(f is None for f in rf):
        raise ValueError("MISSING_RF_RETURN")
    r_by = dict(zip(obs_dates, returns))
    f_by = dict(zip(obs_dates, rf))
    out_w, out_r, out_f, partial, empty = [], [], [], [], []
    for week in weeks:
        if not week.complete:
            partial.append(week.start)
            continue
        valid = [s for s in week.sessions if s in r_by]
        if not valid:
            empty.append(week.start)
            continue
        out_w.append(week.start)
        out_r.append(compound(r_by[s] for s in valid))
        out_f.append(compound(f_by[s] for s in valid))
    return WeeklySeries(out_w, out_r, out_f, partial, empty)


@dataclass(frozen=True)
class WeeklyRatios:
    sharpe: float | None
    sortino: float | None
    sharpe_reason: str | None
    sortino_reason: str | None
    n: int
    shortfalls: int
    downside_periodic: float | None
    downside_annualised: float | None


def weekly_ratios(portfolio: Sequence[float], rf: Sequence[float], factor: int = 52) -> WeeklyRatios:
    """Weekly Sharpe and Sortino, annualised with sqrt(52). Undefined values are None plus a reason."""
    if not portfolio:
        return WeeklyRatios(None, None, "NO_OBSERVATIONS", "NO_OBSERVATIONS", 0, 0, None, None)
    dd = downside_deviation(portfolio, rf, factor)
    s_val = so_val = None
    s_reason = so_reason = None
    try:
        s_val = sharpe(portfolio, rf, factor)
    except Undefined as exc:
        s_reason = exc.reason
    try:
        so_val = sortino(portfolio, rf, factor)
    except Undefined as exc:
        so_reason = exc.reason
    return WeeklyRatios(s_val, so_val, s_reason, so_reason, dd.n, dd.shortfalls, dd.periodic, dd.annualised)
