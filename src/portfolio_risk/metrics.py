"""Pure formulas on already aligned, already validated return lists.

All returns are decimal simple returns (0.01 = 1%). Nothing here reads files, applies
history gates or decides what a user may see; that is :mod:`portfolio_risk.report`.

When a formula is mathematically undefined (a zero denominator, too few points for a
sample standard deviation) it raises :class:`Undefined` with a reason code instead of
returning 0, infinity or NaN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, stdev
from typing import Sequence


class Undefined(ArithmeticError):
    """The statistic does not exist for these inputs; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _check(returns: Sequence[float]) -> None:
    if len(returns) == 0:
        raise Undefined("NO_OBSERVATIONS")
    for r in returns:
        if isinstance(r, bool) or not math.isfinite(r) or r < -1:
            raise ValueError(f"INVALID_SIMPLE_RETURN: {r!r}")


def _check_aligned(returns: Sequence[float], other: Sequence[float]) -> None:
    _check(returns)
    if len(returns) != len(other):
        raise ValueError("RF_INTERVAL_ALIGNMENT_FAILED: series lengths differ")


# --- path measures ------------------------------------------------------------------------

def wealth_index(returns: Sequence[float]) -> list[float]:
    """W_0 = 1 and W_t = W_(t-1) * (1 + r_t). The opening point is part of the path."""
    _check(returns)
    wealth = [1.0]
    for r in returns:
        wealth.append(wealth[-1] * (1.0 + r))
    return wealth


def cumulative_return(returns: Sequence[float]) -> float:
    """Linked return over the period: prod(1 + r_t) - 1. Not annualised."""
    return wealth_index(returns)[-1] - 1.0


def drawdown_series(returns: Sequence[float]) -> list[float]:
    """D_t = W_t / max(W_0..W_t) - 1 for every point, including D_0 = 0."""
    wealth = wealth_index(returns)
    out, peak = [], 0.0
    for w in wealth:
        peak = max(peak, w)
        out.append(w / peak - 1.0 if peak > 0 else -1.0)
    return out


@dataclass(frozen=True)
class DrawdownEvent:
    """The maximum drawdown and where it sits on the wealth path.

    Indices refer to wealth points: 0 is the opening point, i is after return i.
    """

    value: float
    peak_index: int
    trough_index: int
    tied: bool


def max_drawdown(returns: Sequence[float], tie_rule: str = "earliest", rel_tol: float = 1e-12) -> DrawdownEvent:
    """Deepest peak-to-trough fall, signed (<= 0).

    If several points share the deepest value (equal drawdowns or a flat trough),
    ``tie_rule`` picks the earliest or latest trough and ``tied`` is set, so the choice is
    never silent. Which rule is right is an open product decision.
    """
    if tie_rule not in ("earliest", "latest"):
        raise ValueError(f"unknown tie rule {tie_rule!r}")
    dd = drawdown_series(returns)
    worst = min(dd)
    if worst == 0.0:
        return DrawdownEvent(0.0, 0, 0, False)
    candidates = [i for i, d in enumerate(dd) if math.isclose(d, worst, rel_tol=rel_tol, abs_tol=1e-15)]
    trough = candidates[0] if tie_rule == "earliest" else candidates[-1]
    wealth = wealth_index(returns)
    peak_level = max(wealth[: trough + 1])
    peak = max(i for i in range(trough + 1) if wealth[i] == peak_level)
    return DrawdownEvent(dd[trough], peak, trough, len(candidates) > 1)


def current_drawdown(returns: Sequence[float]) -> float:
    """Drawdown of the last point against the highest point of the same window."""
    return drawdown_series(returns)[-1]


# --- dispersion ---------------------------------------------------------------------------

def volatility(returns: Sequence[float], factor: int = 250) -> float:
    """Sample standard deviation (n - 1) of returns, times sqrt(factor)."""
    _check(returns)
    if len(returns) < 2:
        raise Undefined("SD_REQUIRES_TWO_OBSERVATIONS")
    return stdev(returns) * math.sqrt(factor)


@dataclass(frozen=True)
class Downside:
    periodic: float      # sqrt(sum(min(x,0)^2) / N)
    annualised: float    # periodic * sqrt(factor)
    shortfalls: int      # count(r_t < rf_t)
    n: int


def downside_deviation(returns: Sequence[float], rf: Sequence[float], factor: int = 250) -> Downside:
    """Downside deviation against the risk-free return of the same session.

    * shortfall_t = min(r_t - rf_t, 0): a +0.05% day is a shortfall when rf is 0.10%;
      a day exactly at rf is not.
    * The divisor is N, every aligned observation, not just the shortfall days.
    * Zero shortfalls give 0.0: a real number, but Sortino is then undefined.
    """
    _check_aligned(returns, rf)
    excess = [r - f for r, f in zip(returns, rf)]
    periodic = math.sqrt(fmean(min(x, 0.0) ** 2 for x in excess))
    return Downside(periodic, periodic * math.sqrt(factor), sum(x < 0 for x in excess), len(excess))


# --- risk-adjusted ratios -----------------------------------------------------------------

def sharpe(returns: Sequence[float], rf: Sequence[float], factor: int = 250) -> float:
    """mean(x) / sample_sd(x) * sqrt(factor), with x_t = r_t - rf_t.

    The denominator is the SD of *excess* returns, not of raw returns; with a changing
    risk-free rate the two differ.
    """
    _check_aligned(returns, rf)
    if len(returns) < 2:
        raise Undefined("SD_REQUIRES_TWO_OBSERVATIONS")
    excess = [r - f for r, f in zip(returns, rf)]
    sd = stdev(excess)
    if sd == 0:
        raise Undefined("ZERO_EXCESS_SD")
    return fmean(excess) / sd * math.sqrt(factor)


def sortino(returns: Sequence[float], rf: Sequence[float], factor: int = 250) -> float:
    """mean(x) / downside_periodic * sqrt(factor). Same target and same N as downside_deviation.

    Identity used as a reconciliation check:
    ``sortino == factor * mean(x) / downside_deviation(...).annualised``.
    """
    dd = downside_deviation(returns, rf, factor)
    if dd.periodic == 0:
        raise Undefined("ZERO_RF_DOWNSIDE")
    excess = [r - f for r, f in zip(returns, rf)]
    return fmean(excess) / dd.periodic * math.sqrt(factor)


# --- extensions: tail risk and market sensitivity ------------------------------------------

def _tail(returns: Sequence[float], confidence: float) -> list[float]:
    _check(returns)
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    k = math.ceil(len(returns) * (1 - confidence) - 1e-9)
    if k < 1:
        raise Undefined("TAIL_TOO_SMALL")
    return sorted(returns)[:k]


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """One-session historical Value at Risk as a positive loss.

    Convention: the k-th worst return with k = ceil(n * (1 - confidence)); no interpolation.
    With 250 returns at 95%, k = 13: the 13th worst day.
    """
    return -_tail(returns, confidence)[-1]


def historical_es(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Expected shortfall: average loss over the same k worst returns used by the VaR."""
    return -fmean(_tail(returns, confidence))


def beta(returns: Sequence[float], market: Sequence[float], rf: Sequence[float]) -> float:
    """cov(r - rf, m - rf) / var(m - rf) over exactly aligned sessions."""
    _check_aligned(returns, market)
    _check_aligned(returns, rf)
    if len(returns) < 2:
        raise Undefined("SD_REQUIRES_TWO_OBSERVATIONS")
    x = [r - f for r, f in zip(returns, rf)]
    y = [m - f for m, f in zip(market, rf)]
    mx, my = fmean(x), fmean(y)
    var_y = sum((b - my) ** 2 for b in y)
    if var_y == 0:
        raise Undefined("ZERO_MARKET_VARIANCE")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / var_y
