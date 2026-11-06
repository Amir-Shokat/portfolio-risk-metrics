"""Executable mirror of the Gherkin scenarios in docs/features/.

Each test's docstring starts with the scenario title it implements. The last test parses the
feature files and fails if a scenario has no mirror, so the specification and the tests
cannot drift apart silently.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import build, wave

from portfolio_risk import Status, assess, load_contract, metrics as m
from portfolio_risk.inputs import ReturnRow
from portfolio_risk.recovery import count_sessions, find_recovery
from portfolio_risk.riskfree import session_rf
from portfolio_risk.versioning import ResultKey, ResultStore, impacted_metrics
from portfolio_risk.weekly import Week, aggregate_weekly, weekly_ratios

FEATURES = Path(__file__).resolve().parents[1] / "docs" / "features"
RF30 = session_rf(0.30)            # daily risk-free return at a 30% annual YTM, about 0.105%


# --- historical_risk.feature -------------------------------------------------------------

def test_linked_not_added():
    """Scenario: Returns are linked rather than added"""
    assert m.cumulative_return([0.10, -0.10]) == pytest.approx(-0.01)


def test_opening_wealth_in_drawdown():
    """Scenario: Opening wealth is included in drawdown"""
    event = m.max_drawdown([-0.10, 0.05])
    assert event.value == pytest.approx(-0.10)
    assert (event.peak_index, event.trough_index) == (0, 1)


def test_missing_return_not_zero():
    """Scenario: Missing return is not replaced with zero"""
    inputs, _ = build(wave(40), skip={date(2025, 1, 20)})
    report = assess(inputs, "1M")
    offered = [r for r in report.results.values() if r.status is not Status.NOT_OFFERED]
    assert offered and all(r.status is Status.INCOMPLETE_COVERAGE for r in offered)
    assert all(r.value is None and r.diagnostic is None for r in offered)
    assert report.window.coverage()["missing"] == 1


def test_genuine_zero_retained():
    """Scenario: Genuine zero is retained"""
    inputs, dates = build(wave(30), inception=date(2025, 1, 2))
    report = assess(inputs, "1M")
    assert 0.0 in report.window.returns
    assert report["volatility"].n == 30


def test_not_computed_excluded_and_reported():
    """Scenario: Not-computed sessions are excluded and reported"""
    inputs, _ = build(wave(40), not_computed={date(2025, 1, 20)})
    report = assess(inputs, "1M")
    cov = report.window.coverage()
    assert cov["not_computed"] == 1
    assert cov["valid_observations"] == cov["official_sessions"] - 1
    vol = report["volatility"]
    assert vol.status is Status.OK and "NOT_COMPUTED_SESSIONS_EXCLUDED" in vol.reasons


def test_volatility_sample_sd():
    """Scenario: Volatility uses sample standard deviation"""
    assert m.volatility([0.01, -0.01], 1) == pytest.approx(0.0141421356)
    assert m.volatility([0.01, -0.01], 250) == pytest.approx(0.2236068)


def test_downside_rf_target_all_observations():
    """Scenario: Downside deviation uses the risk-free target and all observations"""
    dd = m.downside_deviation([0.0005, 0.002, -0.001, 0.001], [0.001] * 4, 250)
    assert dd.shortfalls == 2 and dd.n == 4
    assert dd.periodic == pytest.approx(math.sqrt((0.0005 ** 2 + 0.002 ** 2) / 4))
    assert dd.periodic == pytest.approx(0.00103078, rel=1e-5)
    assert dd.annualised == pytest.approx(dd.periodic * math.sqrt(250))


def test_sharpe_uses_excess_sd():
    """Scenario: Sharpe uses the standard deviation of excess returns"""
    with pytest.raises(m.Undefined) as exc:
        m.sharpe([0.01, 0.02], [0.0, 0.01])
    assert exc.value.reason == "ZERO_EXCESS_SD"
    assert m.volatility([0.01, 0.02]) > 0


def test_zero_denominator_undefined():
    """Scenario: Zero denominator is undefined, not zero or infinite"""
    values = [0.003 if i % 2 else 0.005 for i in range(250)]
    report = assess(build(values)[0], "1Y")
    sortino = report["sortino"]
    assert sortino.status is Status.UNDEFINED
    assert {"ZERO_RF_DOWNSIDE", "MIN_SHORTFALLS_NOT_MET"} <= set(sortino.reasons)
    assert sortino.value is None and sortino.shortfalls == 0
    assert report["sharpe"].status is Status.OK


def test_volatility_below_gate():
    """Scenario: One-month volatility is withheld below its observation gate"""
    inputs, _ = build(wave(29), inception=date(2025, 1, 3))
    vol = assess(inputs, "1M", as_of=date(2025, 1, 31))["volatility"]
    assert vol.n == 29 and vol.status is Status.INSUFFICIENT_HISTORY
    assert vol.value is None and vol.diagnostic is not None
    assert vol.publication == "withheld" and vol.calculation == "computed"


def test_volatility_at_gate():
    """Scenario: One-month volatility is shown at its observation gate"""
    inputs, _ = build(wave(30), inception=date(2025, 1, 2))
    vol = assess(inputs, "1M", as_of=date(2025, 1, 31))["volatility"]
    assert vol.n == 30 and vol.status is Status.OK
    assert vol.value == pytest.approx(m.volatility(wave(30), 250))


def test_ratio_no_elapsed_day_gate():
    """Scenario: Ratio history has no elapsed-calendar-day gate"""
    inputs, dates = build(wave(250))
    assert (dates[-1] - dates[0]).days < 365
    sharpe = assess(inputs, "1Y")["sharpe"]
    assert sharpe.n == 250 and sharpe.status is Status.OK


def test_ratio_needs_250():
    """Scenario: Ratio history needs 250 observations"""
    sharpe = assess(build(wave(249))[0], "1Y")["sharpe"]
    assert sharpe.status is Status.INSUFFICIENT_HISTORY
    assert sharpe.reasons == ("MIN_OBSERVATIONS_NOT_MET",)


def test_missing_rf_blocks_only_rf_metrics():
    """Scenario: Missing risk-free quote blocks only the metrics that read it"""
    inputs, dates = build(wave(250), drop_rf={date(2025, 4, 1)})
    report = assess(inputs, "1Y")
    assert report["sharpe"].status is Status.RF_MISSING
    assert report["sortino"].status is Status.RF_MISSING
    assert report["volatility"].status is Status.OK


def test_total_loss_policy_pending():
    """Scenario: Total loss is a pending policy, not an invalid number"""
    values = wave(40)
    values[20] = -1.0
    assert assess(build(values)[0], "1M")["volatility"].status is Status.POLICY_PENDING
    values[20] = -1.5
    assert assess(build(values)[0], "1M")["volatility"].status is Status.INVALID_INPUT


def test_return_on_closed_day_invalid():
    """Scenario: A return on a closed day is invalid"""
    holiday = date(2025, 1, 15)
    inputs, _ = build(wave(40), closed={holiday})
    inputs.returns[holiday] = ReturnRow(holiday, 0.001)
    vol = assess(inputs, "1M")["volatility"]
    assert vol.status is Status.INVALID_INPUT and "RETURN_ON_CLOSED_DAY" in vol.reasons


def test_not_offered_for_horizon():
    """Scenario: Metrics not offered for a horizon say so"""
    sharpe = assess(build(wave(300))[0], "1M")["sharpe"]
    assert sharpe.status is Status.NOT_OFFERED and sharpe.publication == "not_offered"


# --- recovery.feature ------------------------------------------------------------------------

SAT, SUN, MON = date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)
WED_BEFORE = date(2025, 12, 31)


def test_recovery_interval_rule():
    """Scenario: Exclude the trough session and include the recovery session"""
    assert count_sessions(SAT, MON, [SAT, SUN, MON]) == 2
    out = find_recovery([WED_BEFORE, SAT, SUN, MON], [-0.10, 0.0, 0.12], [WED_BEFORE, SAT, SUN, MON])
    assert out.state == "recovered" and out.sessions == 2 and out.trough_date == SAT


def test_recovery_closures_not_counted():
    """Scenario: Market closures do not increase recovery duration"""
    assert count_sessions(SAT, MON, [SAT, MON]) == 1
    out = find_recovery([WED_BEFORE, SAT, MON], [-0.10, 0.12], [WED_BEFORE, SAT, MON])
    assert out.sessions == 1


def _recovery_path() -> list[float]:
    # peak on 10 Jan, -5% on 11 Jan, then +0.4% a day: back at the peak after 13 sessions (24 Jan)
    return [0.001] * 10 + [-0.05] + [0.004] * 29


def test_recovery_window_bound():
    """Scenario: Recovery is searched only inside the selected window"""
    inputs, _ = build(_recovery_path())
    past = assess(inputs, "1M", as_of=date(2025, 1, 20))["recovery_sessions"]
    assert past.status is Status.NOT_RECOVERED and past.value is None
    assert past.details["label"] == "not recovered by the end of this period"
    later = assess(inputs, "1M", as_of=date(2025, 1, 31))["recovery_sessions"]
    assert later.status is Status.OK and later.value == 13
    assert later.details["recovery_date"] == date(2025, 1, 24)


def test_no_drawdown_not_zero():
    """Scenario: No drawdown is not a zero-session recovery"""
    report = assess(build([0.001] * 40)[0], "1M")
    assert report["recovery_sessions"].status is Status.NO_DRAWDOWN
    assert report["recovery_sessions"].value is None
    assert report["max_drawdown"].value == 0.0


def test_recovery_missing_coverage():
    """Scenario: Missing coverage is not an observed recovery duration"""
    inputs, _ = build(_recovery_path(), skip={date(2025, 1, 15)})
    rec = assess(inputs, "1M")["recovery_sessions"]
    assert rec.status is Status.INCOMPLETE_COVERAGE


# --- weekly_ratios.feature ---------------------------------------------------------------

WEEK = [date(2026, 1, 3) + timedelta(days=i) for i in range(5)]   # Sat-Wed


def test_weekly_rf_compounds_daily():
    """Scenario: Weekly risk-free return compounds the daily values"""
    series = aggregate_weekly(WEEK, [0.01] * 5, [RF30] * 5, [Week(WEEK[0], tuple(WEEK), True)])
    assert series.rf[0] == pytest.approx(1.30 ** (5 / 250) - 1, rel=1e-12)
    assert series.rf[0] != pytest.approx(1.30 ** (1 / 52) - 1, rel=1e-6)


def test_weekly_excess_not_compounded():
    """Scenario: Daily excess returns are not compounded"""
    r, f = [0.02] * 5, [RF30] * 5
    series = aggregate_weekly(WEEK, r, f, [Week(WEEK[0], tuple(WEEK), True)])
    weekly_excess = series.portfolio[0] - series.rf[0]
    compounded_excess = math.prod(1 + a - b for a, b in zip(r, f)) - 1
    assert weekly_excess == pytest.approx(1.02 ** 5 - 1.30 ** (5 / 250))
    assert abs(weekly_excess - compounded_excess) > 1e-6


def test_weekly_positive_shortfall():
    """Scenario: Positive weekly returns below the weekly risk-free return are shortfalls"""
    assert weekly_ratios([0.001, 0.02, -0.01], [0.005] * 3).shortfalls == 2


def test_weekly_equal_rf_undefined():
    """Scenario: Returns equal to the risk-free return give undefined ratios"""
    out = weekly_ratios([0.01, 0.02, 0.03], [0.01, 0.02, 0.03])
    assert (out.sharpe, out.sortino) == (None, None)
    assert (out.sharpe_reason, out.sortino_reason) == ("ZERO_EXCESS_SD", "ZERO_RF_DOWNSIDE")


def test_weekly_factor_not_a_gate():
    """Scenario: The annualisation factor is not a minimum history"""
    p, f = [0.01, -0.02, 0.015, 0.003, -0.004], [0.005] * 5
    out = weekly_ratios(p, f, 52)
    assert out.n == 5
    assert out.sharpe == pytest.approx(m.sharpe(p, f, 1) * math.sqrt(52))


def test_weekly_policy_pending():
    """Scenario: Weekly ratios stay unpublished until the week policy is approved"""
    report = assess(build(wave(300))[0], "1Y")
    for name in ("sharpe_weekly", "sortino_weekly"):
        res = report[name]
        assert res.status is Status.POLICY_PENDING and res.value is None
        assert res.diagnostic is not None
        assert "PARTIAL_WEEKS_EXCLUDED" in res.reasons and res.details["partial_weeks"] >= 1


# --- change_control.feature --------------------------------------------------------------

def test_report_names_versions():
    """Scenario: Every report names the methodology and policy versions it used"""
    header = assess(build(wave(40))[0], "1M").header()
    assert header["methodology_version"] == "1.3"
    assert header["policy_versions"]["recovery"] == "1.1-window-bound-session-count"
    assert header["policy_versions"]["downside"] == "rf-target-v1"
    assert re.fullmatch(r"[0-9a-f]{12}", header["contract_fingerprint"])


def test_change_impact_map():
    """Scenario: A rule change invalidates only the metrics that depend on it"""
    old = load_contract()
    new = old.with_changes({"metrics.max_drawdown.min_obs": 30})
    assert impacted_metrics(old, new) == {"max_drawdown", "recovery_sessions"}
    assert old.metric_fingerprint("sharpe") == new.metric_fingerprint("sharpe")


REV = {"twr": "twr-r1", "calendar": "cal-r1", "rf": "rf-r1"}


def test_correction_new_dependency():
    """Scenario: Correction creates a new result dependency"""
    c, day = load_contract(), date(2026, 9, 30)
    corrected = {**REV, "rf": "rf-r2"}
    key = lambda metric, rev: ResultKey.build("P001", metric, "1Y", day, c, rev).digest()  # noqa: E731
    assert key("sharpe", REV) != key("sharpe", corrected)
    assert key("volatility", REV) == key("volatility", corrected)


def test_superseded_not_overwritten():
    """Scenario: Published results are superseded, never overwritten"""
    c, day, store = load_contract(), date(2026, 9, 30), ResultStore()
    first = ResultKey.build("P001", "sharpe", "1Y", day, c, REV)
    second = ResultKey.build("P001", "sharpe", "1Y", day, c, {**REV, "rf": "rf-r2"})
    assert store.publish(first, {"value": 1.10})
    assert store.publish(second, {"value": 1.05})
    assert store.current(first.slot) == {"value": 1.05}
    history = store.history(first.slot)
    assert len(history) == 2 and history[0].superseded_by == second.digest()
    assert store.publish(second, {"value": 1.05}) is False
    assert store.get(first) == {"value": 1.10}


# --- the mirror itself -------------------------------------------------------------------

def test_every_scenario_has_a_test():
    titles = {line.strip()[len("Scenario:"):].strip()
              for path in FEATURES.glob("*.feature")
              for line in path.read_text(encoding="utf-8").splitlines()
              if line.strip().startswith("Scenario:")}
    mirrored = {(fn.__doc__ or "").split("Scenario:", 1)[1].strip()
                for name, fn in globals().items()
                if name.startswith("test_") and "Scenario:" in (fn.__doc__ or "")}
    assert len(titles) >= 30
    assert titles == mirrored, f"unmirrored: {titles - mirrored}; stale: {mirrored - titles}"
