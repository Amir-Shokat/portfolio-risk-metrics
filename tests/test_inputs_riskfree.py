"""Input contract, calendar windows and the Treasury-bill conversion."""

from datetime import date

import pytest
from conftest import build, wave

from portfolio_risk import InputError, Status, assess, load_inputs
from portfolio_risk.inputs import shift_months
from portfolio_risk.riskfree import RiskFreeError, compound, normalise_ytm, session_rf


def test_session_rf_uses_250_periods_not_calendar_days():
    assert session_rf(0.30) == pytest.approx(1.30 ** (1 / 250) - 1, rel=1e-12)
    assert session_rf(0.30) == pytest.approx(0.00105001, rel=1e-5)
    # a session after a two-day closure still earns one session, not three calendar days
    assert session_rf(0.30, 1) != pytest.approx((1.30) ** (3 / 365) - 1)


def test_session_rf_compounds_consistently():
    assert compound([session_rf(0.25)] * 5) == pytest.approx(session_rf(0.25, 5), rel=1e-12)


def test_ytm_unit_must_be_declared():
    assert normalise_ytm(30, "percent") == pytest.approx(0.30)
    assert normalise_ytm(0.30, "decimal") == pytest.approx(0.30)
    with pytest.raises(RiskFreeError) as exc:
        normalise_ytm(30, "auto")
    assert exc.value.reason == "RF_UNIT_UNKNOWN"
    with pytest.raises(RiskFreeError):
        normalise_ytm(-120, "percent")
    with pytest.raises(RiskFreeError):
        session_rf(0.3, 0)


def test_invalid_quote_blocks_rf_metrics_as_invalid_input():
    inputs, dates = build(wave(250))
    inputs.rf_ytm[dates[100]] = None              # an unusable quote, not a missing one
    report = assess(inputs, "1Y")
    assert report["sharpe"].status is Status.INVALID_INPUT
    assert report["volatility"].status is Status.OK


def test_month_shift_clamps_to_month_end():
    assert shift_months(date(2025, 3, 31), -1) == date(2025, 2, 28)
    assert shift_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
    assert shift_months(date(2025, 1, 15), -12) == date(2024, 1, 15)


def test_holidays_are_not_padded():
    closed = {date(2025, 1, d) for d in (10, 11, 17, 18, 24, 25)}
    inputs, _ = build(wave(40), closed=closed)
    report = assess(inputs, "1M")
    cov = report.window.coverage()
    assert cov["valid_observations"] == cov["official_sessions"]
    assert not set(report.window.obs_dates) & closed


def test_window_before_first_return_is_not_missing():
    inputs, _ = build(wave(30), inception=date(2025, 1, 10))
    cov = assess(inputs, "1M", as_of=date(2025, 1, 31)).window.coverage()
    assert cov["missing"] == 0 and cov["sessions_before_first_return"] == 9


def test_unknown_calendar_date_is_invalid():
    inputs, dates = build(wave(40))
    del inputs.calendar[dates[20]]
    inputs.sessions.remove(dates[20])
    vol = assess(inputs, "1M")["volatility"]
    assert vol.status is Status.INVALID_INPUT and "UNKNOWN_CALENDAR_DATE" in vol.reasons


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_csv_contract_errors(tmp_path, examples):
    cal, rf = examples / "trading_days.csv", examples / "tbill_ytm.csv"
    cases = {
        "DUPLICATE_DATE": "date,twr,status\n2024-05-05,0.01,ok\n2024-05-05,0.02,ok\n",
        "UNORDERED_DATES": "date,twr,status\n2024-05-06,0.01,ok\n2024-05-05,0.02,ok\n",
        "BLANK_RETURN": "date,twr,status\n2024-05-05,,ok\n",
        "UNEXPECTED_VALUE": "date,twr,status\n2024-05-05,0.01,not_computed\n",
        "MISSING_COLUMN": "date,twr_percent\n2024-05-05,1.0\n",
    }
    for reason, text in cases.items():
        with pytest.raises(InputError) as exc:
            load_inputs(_write(tmp_path, "r.csv", text), cal, rf)
        assert exc.value.reason == reason


def test_rf_file_without_unit_column_is_rejected(tmp_path, examples):
    rf = _write(tmp_path, "rf.csv", "date,yield\n2024-05-05,30\n")
    with pytest.raises(InputError) as exc:
        load_inputs(examples / "daily_returns.csv", examples / "trading_days.csv", rf)
    assert exc.value.reason == "RF_UNIT_UNKNOWN"
