"""Turn aligned inputs into one result per metric: value, status, reasons, evidence.

:func:`assess` is the main entry point. For each metric it

1. collects blocking input reasons for the window (invalid rows, missing sessions, missing
   risk-free or market data, total loss),
2. computes the formula as a *diagnostic* when the inputs allow it, catching undefined cases,
3. applies the contract's horizon and history gates,
4. derives the primary status and publishes the value only when the status is ``OK``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import metrics as m
from .contract import MARKET_METRICS, METRICS, RF_METRICS, Contract, load_contract
from .eligibility import Status, calculation_axis, history_reasons, primary_status, publication_axis
from .inputs import RiskInputs, Window, build_window
from .recovery import find_recovery
from .weekly import aggregate_weekly, plan_weeks, weekly_ratios

_INPUT_BLOCKERS = ("INVALID_SIMPLE_RETURN", "RETURN_ON_CLOSED_DAY", "UNKNOWN_CALENDAR_DATE",
                   "TOTAL_LOSS_POLICY_PENDING", "MISSING_RETURN")
_RF_BLOCKERS = ("INVALID_RF_QUOTE", "MISSING_RF_RETURN")
_MARKET_BLOCKERS = ("INVALID_MARKET_RETURN", "MISSING_MARKET_RETURN")


@dataclass
class MetricResult:
    metric: str
    value: float | None
    status: Status
    reasons: tuple[str, ...]
    diagnostic: float | None
    n: int
    shortfalls: int | None
    unit: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def publication(self) -> str:
        return publication_axis(self.status)

    @property
    def calculation(self) -> str:
        return calculation_axis(self.status, self.diagnostic is not None)

    def to_dict(self, include_diagnostic: bool = False) -> dict[str, Any]:
        out = {
            "metric": self.metric, "value": self.value, "unit": self.unit, "status": self.status.value,
            "reasons": list(self.reasons), "n": self.n, "shortfalls": self.shortfalls,
            "calculation": self.calculation, "publication": self.publication,
            "details": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.details.items()},
        }
        if include_diagnostic:
            out["diagnostic"] = self.diagnostic
        return out


@dataclass
class RiskReport:
    horizon: str
    window: Window
    ratio_window: Window
    results: dict[str, MetricResult]
    contract: Contract

    def __getitem__(self, metric: str) -> MetricResult:
        return self.results[metric]

    def header(self) -> dict[str, Any]:
        return {
            "horizon": self.horizon,
            "window_opening": self.window.opening.isoformat(),
            "window_end": self.window.end.isoformat(),
            "current_window": self.window.is_current,
            "coverage": self.window.coverage(),
            "methodology_version": self.contract.methodology_version,
            "policy_versions": self.contract.policy_versions,
            "contract_fingerprint": self.contract.fingerprint(),
            "ratio_lookback": self.contract.document.get("ratio_lookback", "window"),
        }

    def to_dict(self, include_diagnostic: bool = False) -> dict[str, Any]:
        return {**self.header(), "metrics": [r.to_dict(include_diagnostic) for r in self.results.values()]}


def _blocking(window: Window, metric: str) -> list[str]:
    reasons = [code for code in _INPUT_BLOCKERS if window.flagged(code)]
    if metric in RF_METRICS:
        reasons += [code for code in _RF_BLOCKERS if window.flagged(code)]
    if metric in MARKET_METRICS:
        if not window.has_market_series:
            reasons.append("NO_MARKET_SERIES")
        reasons += [code for code in _MARKET_BLOCKERS if window.flagged(code)]
    return reasons


def _finish(metric: str, contract: Contract, horizon: str, window: Window, reasons: list[str],
            diagnostic: float | None, n: int, shortfalls: int | None = None,
            details: dict[str, Any] | None = None, gate: bool = True) -> MetricResult:
    rule = contract.rule(metric)
    if not contract.offered(metric, horizon):
        reasons.insert(0, "NOT_OFFERED_FOR_HORIZON")
    if gate:
        reasons += history_reasons(n, rule.get("min_obs"), shortfalls, rule.get("min_shortfalls"))
    if window.not_computed:
        reasons.append("NOT_COMPUTED_SESSIONS_EXCLUDED")
    reasons = list(dict.fromkeys(reasons))
    status = primary_status(reasons)
    value = diagnostic if status is Status.OK else None
    return MetricResult(metric, value, status, tuple(reasons), diagnostic, n, shortfalls,
                        rule.get("unit", "decimal"), details or {})


def _assess_metric(metric: str, contract: Contract, horizon: str, w: Window, rw: Window,
                   inputs: RiskInputs) -> MetricResult:
    win = rw if metric in ("sharpe", "sortino") else w
    reasons = _blocking(win, metric)
    blocked = bool(reasons)
    r, rf, n = win.returns, win.rf, len(win.returns)
    diag: float | None = None
    shortfalls: int | None = None
    details: dict[str, Any] = {}
    daily = contract.daily_factor

    if contract.rule(metric).get("scope") == "extension":
        reasons.append("EXTENSION_METRIC")
    if metric in ("sharpe", "sortino") and rw is not w:
        reasons.append("RATIO_LOOKBACK_LAST_N")
        details.update(ratio_window_opening=rw.opening, ratio_window_end=rw.end)

    if not blocked:
        try:
            if metric == "cumulative_twr":
                diag = m.cumulative_return(r)
            elif metric == "max_drawdown":
                event = m.max_drawdown(r, contract.recovery_tie_rule)
                diag = event.value
                if event.value < 0:
                    pts = win.point_dates
                    details.update(peak_date=pts[event.peak_index], trough_date=pts[event.trough_index])
                if event.tied:
                    reasons.append("TIE_RULE_APPLIED")
            elif metric == "current_drawdown":
                diag = m.current_drawdown(r)
            elif metric == "recovery_sessions":
                out = find_recovery(win.point_dates, r, inputs.sessions, contract.recovery_tie_rule)
                details.update(drawdown=out.drawdown, peak_date=out.peak_date, trough_date=out.trough_date,
                               recovery_date=out.recovery_date)
                if out.tied:
                    reasons.append("TIE_RULE_APPLIED")
                if out.state == "no_drawdown":
                    reasons.append("NO_DRAWDOWN_EVENT")
                elif out.state == "not_recovered":
                    reasons.append("NOT_RECOVERED_IN_WINDOW")
                    policy = contract.document["policies"]["recovery"]
                    details["label"] = policy["label_current_window" if win.is_current else "label_historical_window"]
                else:
                    diag = float(out.sessions)
            elif metric == "volatility":
                diag = m.volatility(r, daily)
            elif metric == "downside_deviation":
                dd = m.downside_deviation(r, rf, daily)
                diag, shortfalls = dd.annualised, dd.shortfalls
                details["periodic"] = dd.periodic
            elif metric == "sharpe":
                diag = m.sharpe(r, rf, daily)
            elif metric == "sortino":
                dd = m.downside_deviation(r, rf, daily)
                shortfalls = dd.shortfalls
                details["downside_annualised"] = dd.annualised
                diag = m.sortino(r, rf, daily)
            elif metric in ("sharpe_weekly", "sortino_weekly"):
                policy = contract.document["policies"]["weekly"]
                weeks = plan_weeks(win.sessions, inputs.sessions, win.opening, win.end, policy["week_start"])
                series = aggregate_weekly(win.obs_dates, r, rf, weeks)
                ratios = weekly_ratios(series.portfolio, series.rf, contract.weekly_factor)
                n = ratios.n
                details.update(weeks_used=ratios.n, partial_weeks=len(series.partial_weeks),
                               weeks_without_valid_sessions=len(series.empty_weeks))
                if series.partial_weeks:
                    reasons.append("PARTIAL_WEEKS_EXCLUDED")
                if metric == "sharpe_weekly":
                    diag = ratios.sharpe
                    if ratios.sharpe_reason:
                        reasons.append(ratios.sharpe_reason)
                else:
                    diag, shortfalls = ratios.sortino, ratios.shortfalls
                    if ratios.sortino_reason:
                        reasons.append(ratios.sortino_reason)
                reasons.append("WEEKLY_POLICY_PENDING")
            elif metric == "var_95":
                diag = m.historical_var(r, contract.var_confidence)
            elif metric == "es_95":
                diag = m.historical_es(r, contract.var_confidence)
            elif metric == "beta":
                diag = m.beta(r, win.market, rf)
        except m.Undefined as exc:
            reasons.append(exc.reason)
    return _finish(metric, contract, horizon, win, reasons, diag, n, shortfalls, details)


def assess(inputs: RiskInputs, horizon: str = "1Y", as_of: date | None = None,
           contract: Contract | None = None, ratio_lookback: str | None = None) -> RiskReport:
    """Assess every metric for one horizon.

    ``ratio_lookback`` overrides the contract: ``"window"`` computes daily Sharpe and
    Sortino on the selected window; ``"last_n"`` uses the most recent N valid sessions,
    where N is the ratio-history minimum (250).
    """
    contract = contract or load_contract()
    if ratio_lookback is not None:
        contract = contract.with_changes({"ratio_lookback": ratio_lookback})
    if horizon not in contract.horizons:
        raise ValueError(f"unknown horizon {horizon!r}; use one of {sorted(contract.horizons)}")
    policy = contract.not_computed_policy
    window = build_window(inputs, as_of, months=contract.horizons[horizon], label=horizon,
                          not_computed_policy=policy, rf_periods=contract.rf_periods_per_year)
    lookback = contract.document.get("ratio_lookback", "window")
    if lookback == "window":
        ratio_window = window
    elif lookback == "last_n":
        ratio_window = build_window(inputs, as_of, last_valid=contract.ratio_min_obs, label="ratio",
                                    not_computed_policy=policy, rf_periods=contract.rf_periods_per_year)
    else:
        raise ValueError(f"unknown ratio_lookback {lookback!r}")
    results = {metric: _assess_metric(metric, contract, horizon, window, ratio_window, inputs)
               for metric in METRICS if metric in contract.document["metrics"]}
    return RiskReport(horizon, window, ratio_window, results, contract)
