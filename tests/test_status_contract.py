"""Status precedence, gates, the methodology contract and the command line."""

import json
from datetime import date

import pytest
from conftest import build, wave

from portfolio_risk import Status, assess, load_contract, load_inputs
from portfolio_risk.cli import main
from portfolio_risk.eligibility import calculation_axis, history_reasons, primary_status, publication_axis
from portfolio_risk.versioning import ResultKey, impacted_metrics


def test_precedence_input_and_math_before_history():
    assert primary_status(["MIN_OBSERVATIONS_NOT_MET", "MISSING_RETURN"]) is Status.INCOMPLETE_COVERAGE
    assert primary_status(["MIN_SHORTFALLS_NOT_MET", "ZERO_RF_DOWNSIDE"]) is Status.UNDEFINED
    assert primary_status(["MISSING_RF_RETURN", "NOT_OFFERED_FOR_HORIZON"]) is Status.NOT_OFFERED
    assert primary_status(["EXTENSION_METRIC", "TIE_RULE_APPLIED"]) is Status.OK
    with pytest.raises(ValueError):
        primary_status(["SOMETHING_NEW"])


def test_gates_are_inclusive():
    assert history_reasons(30, 30) == []
    assert history_reasons(29, 30) == ["MIN_OBSERVATIONS_NOT_MET"]
    assert history_reasons(250, 250, 30, 30) == []
    assert history_reasons(250, 250, 29, 30) == ["MIN_SHORTFALLS_NOT_MET"]
    assert history_reasons(250, 250, None, 30) == []        # unknown count is not "too few"


def test_three_axes():
    assert calculation_axis(Status.INSUFFICIENT_HISTORY, True) == "computed"
    assert calculation_axis(Status.RF_MISSING, False) == "missing_input"
    assert publication_axis(Status.NOT_RECOVERED) == "eligible"
    assert publication_axis(Status.POLICY_PENDING) == "withheld"


def test_downside_needs_30_shortfalls():
    # +0.2% days are above the 0.105% risk-free return; -0.1% days are shortfalls
    values = [0.002] * 40 + [-0.001] * 29
    report = assess(build(values)[0], "3M")
    dd = report["downside_deviation"]
    assert dd.shortfalls == 29 and dd.status is Status.INSUFFICIENT_SHORTFALLS
    values = [0.002] * 40 + [-0.001] * 30
    assert assess(build(values)[0], "3M")["downside_deviation"].status is Status.OK


def test_contract_defaults():
    c = load_contract()
    assert c.methodology_version == "1.3"
    assert (c.daily_factor, c.weekly_factor, c.rf_periods_per_year) == (250, 52, 250)
    assert c.ratio_min_obs == 250 and c.rule("sortino")["min_shortfalls"] == 30
    assert c.offered("sharpe", "1Y") and not c.offered("sharpe", "6M")


def test_annualisation_change_touches_only_scaled_metrics():
    old = load_contract()
    new = old.with_changes({"annualization.daily": 240})
    assert impacted_metrics(old, new) == {"volatility", "downside_deviation", "sharpe", "sortino"}
    assert old.fingerprint() != new.fingerprint()


def test_contract_validation(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"methodology_version": "9"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required sections"):
        load_contract(path)
    doc = load_contract().document | {"metrics": {"omega": {}}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="does not implement"):
        load_contract(path)


def test_result_key_requires_input_revisions():
    with pytest.raises(ValueError, match="market"):
        ResultKey.build("P001", "beta", "1Y", date(2026, 9, 30), load_contract(),
                        {"twr": "a", "calendar": "b", "rf": "c"})


def test_last_n_lookback_reaches_250_when_the_window_is_short(examples):
    inputs = load_inputs(examples / "daily_returns.csv", examples / "trading_days.csv",
                         examples / "tbill_ytm.csv", examples / "market_index.csv")
    window = assess(inputs, "6M")
    assert window["sharpe"].n == 132 and window["sharpe"].status is Status.NOT_OFFERED
    last_n = assess(inputs, "6M", ratio_lookback="last_n")
    assert last_n["sharpe"].n == 250 and last_n["sharpe"].status is Status.NOT_OFFERED
    assert last_n["sharpe"].diagnostic is not None
    assert "RATIO_LOOKBACK_LAST_N" in last_n["sharpe"].reasons


def test_example_regression(examples):
    """Pinned values on the synthetic examples; a change here needs a methodology note."""
    inputs = load_inputs(examples / "daily_returns.csv", examples / "trading_days.csv",
                         examples / "tbill_ytm.csv", examples / "market_index.csv")
    r = assess(inputs, "1Y")
    assert r.window.coverage() == {"official_sessions": 258, "valid_observations": 256, "not_computed": 2,
                                   "missing": 0, "rf_aligned": 256, "sessions_before_first_return": 0}
    assert r["max_drawdown"].value == pytest.approx(-0.13863, abs=1e-5)
    assert r["volatility"].value == pytest.approx(0.17629, abs=1e-5)
    assert r["recovery_sessions"].value == 25
    assert r["var_95"].value == pytest.approx(0.015806)
    # the March 2025 quote is missing: a past window that contains it blocks rf metrics only
    past = assess(inputs, "1Y", as_of=date(2025, 6, 30))
    assert past["downside_deviation"].reasons == ("MISSING_RF_RETURN",)
    assert past["volatility"].status is Status.OK and not past.window.is_current


def _args(examples, *extra):
    return ["--returns", str(examples / "daily_returns.csv"), "--rf", str(examples / "tbill_ytm.csv"),
            "--calendar", str(examples / "trading_days.csv"), "--market", str(examples / "market_index.csv"),
            *extra]


def test_cli_table_and_json(examples, capsys):
    assert main(_args(examples, "--horizon", "6M")) == 0
    out = capsys.readouterr().out
    assert "methodology 1.3" in out and "recovery_sessions" in out
    assert main(_args(examples, "--horizon", "1y", "--json", "--diagnostics")) == 0
    payload = json.loads(capsys.readouterr().out)
    sharpe = next(x for x in payload["metrics"] if x["metric"] == "sharpe")
    assert sharpe["value"] is not None and sharpe["diagnostic"] is not None


def test_cli_input_error_exit_code(tmp_path, examples, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("date,twr\n2024-05-05,abc\n", encoding="utf-8")
    args = _args(examples)
    args[1] = str(bad)
    assert main(args) == 2
    assert "INVALID_NUMBER" in capsys.readouterr().err
