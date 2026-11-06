"""History gates, reason codes and the user-facing status of each metric.

Design rules carried over from the original specification:

* A value that cannot be shown is ``None`` plus a status, never a fake 0.
* Every applicable reason is kept. A Sortino can be both undefined (no shortfall) and
  short of the 30-shortfall gate; both reasons are reported.
* Input and mathematical failures take precedence over history gates, so an undefined
  ratio is never mislabelled as "not enough history", and missing data is never
  mislabelled as a young account.
* "Not offered for this horizon" is a product rule, not a calculation failure.
* A value computed below its gate is kept as a *diagnostic* for internal review but is
  not published.

The original design kept three separate axes (calculation, quality, publication). The
primary :class:`Status` below is the single user-facing summary; :func:`calculation_axis`
and :func:`publication_axis` recover the other two views.
"""

from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    OK = "OK"
    NOT_OFFERED = "NOT_OFFERED"
    INVALID_INPUT = "INVALID_INPUT"
    POLICY_PENDING = "POLICY_PENDING"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
    RF_MISSING = "RF_MISSING"
    MARKET_MISSING = "MARKET_MISSING"
    UNDEFINED = "UNDEFINED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_SHORTFALLS = "INSUFFICIENT_SHORTFALLS"
    NO_DRAWDOWN = "NO_DRAWDOWN"
    NOT_RECOVERED = "NOT_RECOVERED"


#: Reason code -> status, in precedence order (first match decides the primary status).
REASON_PRECEDENCE: tuple[tuple[str, Status], ...] = (
    ("NOT_OFFERED_FOR_HORIZON", Status.NOT_OFFERED),
    ("INVALID_SIMPLE_RETURN", Status.INVALID_INPUT),
    ("RETURN_ON_CLOSED_DAY", Status.INVALID_INPUT),
    ("UNKNOWN_CALENDAR_DATE", Status.INVALID_INPUT),
    ("INVALID_RF_QUOTE", Status.INVALID_INPUT),
    ("INVALID_MARKET_RETURN", Status.INVALID_INPUT),
    ("TOTAL_LOSS_POLICY_PENDING", Status.POLICY_PENDING),
    ("MISSING_RETURN", Status.INCOMPLETE_COVERAGE),
    ("MISSING_RF_RETURN", Status.RF_MISSING),
    ("MISSING_MARKET_RETURN", Status.MARKET_MISSING),
    ("NO_MARKET_SERIES", Status.MARKET_MISSING),
    ("ZERO_EXCESS_SD", Status.UNDEFINED),
    ("ZERO_RF_DOWNSIDE", Status.UNDEFINED),
    ("ZERO_MARKET_VARIANCE", Status.UNDEFINED),
    ("NO_OBSERVATIONS", Status.INSUFFICIENT_HISTORY),
    ("SD_REQUIRES_TWO_OBSERVATIONS", Status.INSUFFICIENT_HISTORY),
    ("TAIL_TOO_SMALL", Status.INSUFFICIENT_HISTORY),
    ("MIN_OBSERVATIONS_NOT_MET", Status.INSUFFICIENT_HISTORY),
    ("MIN_SHORTFALLS_NOT_MET", Status.INSUFFICIENT_SHORTFALLS),
    ("WEEKLY_POLICY_PENDING", Status.POLICY_PENDING),
    ("NO_DRAWDOWN_EVENT", Status.NO_DRAWDOWN),
    ("NOT_RECOVERED_IN_WINDOW", Status.NOT_RECOVERED),
)

#: Reasons that inform but do not change the status.
INFORMATIONAL = frozenset({
    "TIE_RULE_APPLIED",
    "NOT_COMPUTED_SESSIONS_EXCLUDED",
    "PARTIAL_WEEKS_EXCLUDED",
    "EXTENSION_METRIC",
    "RATIO_LOOKBACK_LAST_N",
})

_STATUS_OF = dict(REASON_PRECEDENCE)
_ORDER = {code: i for i, (code, _) in enumerate(REASON_PRECEDENCE)}

#: Statuses whose meaning may be shown to the user even though there is no number.
PUBLISHABLE = frozenset({Status.OK, Status.NO_DRAWDOWN, Status.NOT_RECOVERED})


def primary_status(reasons: list[str] | tuple[str, ...]) -> Status:
    """The highest-precedence status among the reasons; OK if only informational reasons."""
    decisive = [r for r in reasons if r in _STATUS_OF]
    if not decisive:
        unknown = [r for r in reasons if r not in INFORMATIONAL]
        if unknown:
            raise ValueError(f"unknown reason codes: {unknown}")
        return Status.OK
    return _STATUS_OF[min(decisive, key=_ORDER.__getitem__)]


def history_reasons(n: int, min_obs: int | None, shortfalls: int | None = None,
                    min_shortfalls: int | None = None) -> list[str]:
    """Gate check. Boundaries are inclusive: 30 observations pass a 30-observation gate.

    An unknown shortfall count (the formula was blocked by an input problem) is not
    reported as too few shortfalls.
    """
    reasons = []
    if min_obs is not None and n < min_obs:
        reasons.append("MIN_OBSERVATIONS_NOT_MET")
    if min_shortfalls is not None and shortfalls is not None and shortfalls < min_shortfalls:
        reasons.append("MIN_SHORTFALLS_NOT_MET")
    return reasons


def calculation_axis(status: Status, has_diagnostic: bool) -> str:
    """The 'could a valid number be calculated?' view of a result."""
    if status is Status.INVALID_INPUT:
        return "invalid_input"
    if status in (Status.INCOMPLETE_COVERAGE, Status.RF_MISSING, Status.MARKET_MISSING):
        return "missing_input"
    if status is Status.UNDEFINED:
        return "undefined"
    if status is Status.POLICY_PENDING and not has_diagnostic:
        return "policy_pending"
    if has_diagnostic or status in (Status.NO_DRAWDOWN, Status.NOT_RECOVERED):
        return "computed"
    return "insufficient_observations"


def publication_axis(status: Status) -> str:
    """The 'may this appear in the product?' view of a result."""
    if status is Status.NOT_OFFERED:
        return "not_offered"
    return "eligible" if status in PUBLISHABLE else "withheld"
