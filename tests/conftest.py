"""Shared builders for small, hand-checkable input sets.

The toy calendar treats every day as a session unless it is listed in ``closed``, so
session counts in the tests can be checked by counting days.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import pytest

from portfolio_risk import make_inputs

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def wave(n: int, scale: float = 0.002) -> list[float]:
    """A deterministic, non-constant return pattern: -2, -1, 0, 1, 2 times ``scale``, repeated."""
    return [scale * ((i * 7) % 5 - 2) for i in range(n)]


def build(
    values: Sequence[float],
    inception: date = date(2025, 1, 1),
    closed: Iterable[date] = (),
    ytm: float = 0.30,
    market: Sequence[float] | None = None,
    drop_rf: Iterable[date] = (),
    not_computed: Iterable[date] = (),
    skip: Iterable[date] = (),
    lead_days: int = 400,
):
    """Return ``(inputs, dates)``.

    Values are placed on consecutive sessions from ``inception``. A date in ``skip`` gets
    no row at all (a missing session); a date in ``not_computed`` gets a not_computed row.
    Neither consumes a value. The calendar starts ``lead_days`` before inception so that
    long windows are fully covered by the calendar.
    """
    closed, skip, not_computed = set(closed), set(skip), set(not_computed)
    rows: dict[date, float | None] = {}
    dates: list[date] = []
    d, i = inception, 0
    while i < len(values):
        if d not in closed:
            if d in not_computed:
                rows[d] = None
            elif d not in skip:
                rows[d] = values[i]
                dates.append(d)
                i += 1
        d += timedelta(days=1)
    end = d - timedelta(days=1)
    start = inception - timedelta(days=lead_days)
    every = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    sessions = [x for x in every if x not in closed]
    drop_rf = set(drop_rf)
    quotes = {s: ytm for s in sessions if s not in drop_rf}
    mkt = dict(zip(dates, market)) if market is not None else None
    return make_inputs(rows, sessions, closed=[x for x in every if x in closed], ytm=quotes, market=mkt), dates


@pytest.fixture
def examples() -> Path:
    return EXAMPLES
