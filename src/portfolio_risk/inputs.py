"""Input contract: daily TWR, the official trading calendar and the risk-free quotes.

This package starts where the upstream return service ends. It receives a series of
daily cash-flow-adjusted simple TWR values and does not rebuild them from balances,
trades or cash flows. Its job is to check that the series is fit for a risk calculation
and to line it up, session by session, with the calendar and the risk-free series.

Files (CSV, UTF-8, ISO dates):

``returns``   ``date,twr,status``  - ``twr`` in decimals (0.012 = 1.2%); ``status`` is ``ok``
              or ``not_computed`` (the upstream service could not define a return for that
              session, e.g. opening capital below its minimum; ``twr`` is then empty).
``calendar``  ``date,session``      - every calendar date, ``open`` or ``closed``.
``rf``        ``date,ytm`` or ``date,ytm_percent`` - annual Treasury-bill YTM; the column
              name declares the unit.
``market``    ``date,return``       - optional daily return of a market index (for beta).

Rules enforced here, all from the original specification:

* A session without a row is **missing**. It is never filled with 0 and never dropped
  silently; it blocks the window (``MISSING_RETURN``).
* A ``not_computed`` session is excluded from the sample *and reported*; it is not a zero.
* Holidays are not padded with zero returns. A session on which the investor did not
  trade is still a session.
* A return dated on a closed day, or on a date the calendar does not know, is invalid.
* A missing risk-free quote is never replaced by 0, by yesterday's quote or by today's
  rate. It blocks the metrics that need it, and only those.
* Returns below -100% are invalid. Exactly -100% is a real total loss whose display
  policy is still open (``TOTAL_LOSS_POLICY_PENDING``).
* Extreme but valid returns are kept.
* Unparseable files, duplicate dates and unordered rows break the contract and raise
  :class:`InputError` instead of producing numbers.
"""

from __future__ import annotations

import bisect
import calendar as _cal
import csv
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from .riskfree import RiskFreeError, normalise_ytm, session_rf


class InputError(ValueError):
    """The input files do not satisfy the contract."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class ReturnRow:
    date: date
    value: float | None
    status: str = "ok"            # "ok" | "not_computed"


@dataclass
class RiskInputs:
    """Everything the calculation needs, keyed by date."""

    returns: dict[date, ReturnRow]
    calendar: dict[date, bool]                      # True = official session
    rf_ytm: dict[date, float | None]                # decimal annual YTM; None = unusable quote
    market: dict[date, float] | None = None
    revisions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.sessions: list[date] = sorted(d for d, is_open in self.calendar.items() if is_open)

    @property
    def first_date(self) -> date:
        return min(self.returns)

    @property
    def last_date(self) -> date:
        return max(self.returns)


# --- building from Python objects or CSV ----------------------------------------------------

def make_inputs(
    returns: Mapping[date, float | None] | Iterable[ReturnRow],
    sessions: Iterable[date],
    closed: Iterable[date] = (),
    ytm: Mapping[date, float] | None = None,
    ytm_unit: str = "decimal",
    market: Mapping[date, float] | None = None,
    revisions: Mapping[str, str] | None = None,
) -> RiskInputs:
    """Convenience constructor for tests and notebooks.

    ``returns`` maps a date to a decimal return, or to ``None`` for a ``not_computed``
    session. Omit a session entirely to model a missing row.
    """
    if isinstance(returns, Mapping):
        rows = {d: ReturnRow(d, v, "ok" if v is not None else "not_computed") for d, v in returns.items()}
    else:
        rows = {}
        for row in returns:
            if row.date in rows:
                raise InputError("DUPLICATE_DATE", str(row.date))
            rows[row.date] = row
    cal = {d: False for d in closed}
    cal.update({d: True for d in sessions})
    rf: dict[date, float | None] = {}
    for d, q in (ytm or {}).items():
        try:
            rf[d] = normalise_ytm(q, ytm_unit)
        except RiskFreeError:
            rf[d] = None
    return RiskInputs(dict(sorted(rows.items())), cal, rf, dict(market) if market is not None else None,
                      dict(revisions or {}))


def _read(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return [h.strip() for h in (reader.fieldnames or [])], rows


def _date(text: str, where: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except (AttributeError, ValueError):
        raise InputError("INVALID_DATE", f"{where}: {text!r}") from None


def _float(text: str, where: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        raise InputError("INVALID_NUMBER", f"{where}: {text!r}") from None


def _ordered_unique(dates: list[date], where: str) -> None:
    seen = set()
    for d in dates:
        if d in seen:
            raise InputError("DUPLICATE_DATE", f"{where}: {d}")
        seen.add(d)
    if dates != sorted(dates):
        raise InputError("UNORDERED_DATES", where)


def read_returns_csv(path: str | Path) -> dict[date, ReturnRow]:
    headers, rows = _read(path)
    if "date" not in headers or "twr" not in headers:
        raise InputError("MISSING_COLUMN", f"{path}: need 'date' and 'twr' (decimal); percent is not accepted")
    out: dict[date, ReturnRow] = {}
    for i, row in enumerate(rows, start=2):
        where = f"{Path(path).name} line {i}"
        d = _date(row["date"], where)
        status = (row.get("status") or "ok").strip()
        raw = (row["twr"] or "").strip()
        if status == "ok":
            if not raw:
                raise InputError("BLANK_RETURN", f"{where}: status ok needs a value (use not_computed)")
            out_row = ReturnRow(d, _float(raw, where), "ok")
        elif status == "not_computed":
            if raw:
                raise InputError("UNEXPECTED_VALUE", f"{where}: not_computed rows carry no value")
            out_row = ReturnRow(d, None, "not_computed")
        else:
            raise InputError("UNKNOWN_ROW_STATUS", f"{where}: {status!r}")
        if d in out:
            raise InputError("DUPLICATE_DATE", f"{where}: {d}")
        out[d] = out_row
    _ordered_unique(list(out), Path(path).name)
    return out


def read_calendar_csv(path: str | Path) -> dict[date, bool]:
    headers, rows = _read(path)
    if "date" not in headers or "session" not in headers:
        raise InputError("MISSING_COLUMN", f"{path}: need 'date' and 'session'")
    out: dict[date, bool] = {}
    for i, row in enumerate(rows, start=2):
        where = f"{Path(path).name} line {i}"
        d = _date(row["date"], where)
        value = row["session"].strip().lower()
        if value not in ("open", "closed", "1", "0"):
            raise InputError("UNKNOWN_SESSION_FLAG", f"{where}: {value!r}")
        if d in out:
            raise InputError("DUPLICATE_DATE", f"{where}: {d}")
        out[d] = value in ("open", "1")
    return out


def read_ytm_csv(path: str | Path) -> dict[date, float | None]:
    headers, rows = _read(path)
    if "ytm" in headers:
        column, unit = "ytm", "decimal"
    elif "ytm_percent" in headers:
        column, unit = "ytm_percent", "percent"
    else:
        raise InputError("RF_UNIT_UNKNOWN", f"{path}: need a 'ytm' (decimal) or 'ytm_percent' column")
    out: dict[date, float | None] = {}
    for i, row in enumerate(rows, start=2):
        where = f"{Path(path).name} line {i}"
        d = _date(row["date"], where)
        if d in out:
            raise InputError("DUPLICATE_DATE", f"{where}: {d}")
        try:
            out[d] = normalise_ytm(_float(row[column], where), unit)
        except RiskFreeError:
            out[d] = None
    return out


def read_market_csv(path: str | Path) -> dict[date, float]:
    headers, rows = _read(path)
    if "date" not in headers or "return" not in headers:
        raise InputError("MISSING_COLUMN", f"{path}: need 'date' and 'return' (decimal)")
    out: dict[date, float] = {}
    for i, row in enumerate(rows, start=2):
        where = f"{Path(path).name} line {i}"
        d = _date(row["date"], where)
        if d in out:
            raise InputError("DUPLICATE_DATE", f"{where}: {d}")
        out[d] = _float(row["return"], where)
    return out


def load_inputs(returns: str | Path, calendar: str | Path, rf: str | Path,
                market: str | Path | None = None, revisions: Mapping[str, str] | None = None) -> RiskInputs:
    """Read the CSV files into :class:`RiskInputs`."""
    return RiskInputs(read_returns_csv(returns), read_calendar_csv(calendar), read_ytm_csv(rf),
                      read_market_csv(market) if market else None, dict(revisions or {}))


# --- windows -----------------------------------------------------------------------------------

def shift_months(d: date, months: int) -> date:
    """Calendar-month shift with month-end clamping (31 March - 1 month = 28/29 February)."""
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


@dataclass
class Window:
    """One selected period, aligned session by session."""

    label: str
    opening: date                      # wealth point W_0 sits here (exclusive boundary)
    end: date
    sessions: list[date]               # official sessions in (opening, end] after inception
    obs_dates: list[date]              # sessions with a valid return
    returns: list[float]
    rf: list[float | None]             # per-session risk-free return aligned with obs_dates
    market: list[float | None]
    not_computed: list[date] = field(default_factory=list)
    missing: list[date] = field(default_factory=list)
    pre_inception: int = 0
    reasons: dict[str, list[date]] = field(default_factory=dict)   # problems found, with dates
    is_current: bool = True
    has_market_series: bool = False

    def flagged(self, code: str) -> bool:
        return bool(self.reasons.get(code))

    @property
    def point_dates(self) -> list[date]:
        return [self.opening] + self.obs_dates

    def coverage(self) -> dict[str, int]:
        return {
            "official_sessions": len(self.sessions),
            "valid_observations": len(self.obs_dates),
            "not_computed": len(self.not_computed),
            "missing": len(self.missing),
            "rf_aligned": sum(f is not None for f in self.rf),
            "sessions_before_first_return": self.pre_inception,
        }


def _previous_session(sessions: list[date], d: date) -> date | None:
    i = bisect.bisect_left(sessions, d)
    return sessions[i - 1] if i > 0 else None


def build_window(inputs: RiskInputs, as_of: date | None = None, months: int | None = None,
                 last_valid: int | None = None, label: str = "", not_computed_policy: str = "exclude_and_report",
                 rf_periods: int = 250) -> Window:
    """Align returns, risk-free and market data for one window.

    Give either ``months`` (a trailing calendar window, e.g. 12 for 1Y) or ``last_valid``
    (walk back until that many valid observations are found; used only when the contract's
    ``ratio_lookback`` is set to ``last_n``).
    """
    if (months is None) == (last_valid is None):
        raise ValueError("give exactly one of months or last_valid")
    end = as_of or inputs.last_date
    inception = inputs.first_date
    reasons: dict[str, list[date]] = {}

    def flag(code: str, d: date) -> None:
        reasons.setdefault(code, []).append(d)

    if months is not None:
        boundary = shift_months(end, -months)
        candidate = [s for s in inputs.sessions if boundary < s <= end]
    else:
        upto = inputs.sessions[: bisect.bisect_right(inputs.sessions, end)]
        candidate, valid = [], 0
        for s in reversed(upto):
            if s < inception or valid >= last_valid:
                break
            candidate.append(s)
            row = inputs.returns.get(s)
            valid += bool(row and row.status == "ok")
        candidate.reverse()
        boundary = _previous_session(inputs.sessions, candidate[0]) if candidate else end
        boundary = boundary or (candidate[0] - timedelta(days=1))

    sessions = [s for s in candidate if s >= inception]
    pre_inception = len(candidate) - len(sessions)
    opening = boundary
    if pre_inception:
        opening = _previous_session(inputs.sessions, sessions[0]) if sessions else boundary
        opening = opening or (sessions[0] - timedelta(days=1))

    # the calendar must know every date of the window
    d = opening + timedelta(days=1)
    while d <= end:
        if d not in inputs.calendar:
            flag("UNKNOWN_CALENDAR_DATE", d)
        d += timedelta(days=1)
    # rows dated on closed days inside the window
    for rd in inputs.returns:
        if opening < rd <= end and inputs.calendar.get(rd) is False:
            flag("RETURN_ON_CLOSED_DAY", rd)

    obs_dates, values, rf, market, not_computed, missing = [], [], [], [], [], []
    for s in sessions:
        row = inputs.returns.get(s)
        if row is None:
            missing.append(s)
            flag("MISSING_RETURN", s)
            continue
        if row.status == "not_computed":
            if not_computed_policy == "block_window":
                missing.append(s)
                flag("MISSING_RETURN", s)
            else:
                not_computed.append(s)
                flag("NOT_COMPUTED_SESSIONS_EXCLUDED", s)
            continue
        v = row.value
        if v is None or isinstance(v, bool) or not math.isfinite(v) or v < -1:
            flag("INVALID_SIMPLE_RETURN", s)
            continue
        if v == -1:
            flag("TOTAL_LOSS_POLICY_PENDING", s)
        obs_dates.append(s)
        values.append(float(v))
        if s not in inputs.rf_ytm:
            rf.append(None)
            flag("MISSING_RF_RETURN", s)
        elif inputs.rf_ytm[s] is None:
            rf.append(None)
            flag("INVALID_RF_QUOTE", s)
        else:
            rf.append(session_rf(inputs.rf_ytm[s], 1, rf_periods))
        if inputs.market is not None:
            m = inputs.market.get(s)
            if m is None:
                market.append(None)
                flag("MISSING_MARKET_RETURN", s)
            elif not math.isfinite(m) or m < -1:
                market.append(None)
                flag("INVALID_MARKET_RETURN", s)
            else:
                market.append(m)
        else:
            market.append(None)

    return Window(
        label=label or (f"{months}M" if months else f"last {last_valid}"),
        opening=opening, end=end, sessions=sessions, obs_dates=obs_dates, returns=values, rf=rf,
        market=market, not_computed=not_computed, missing=missing, pre_inception=pre_inception,
        reasons=reasons, is_current=end >= inputs.last_date, has_market_series=inputs.market is not None,
    )
