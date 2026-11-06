"""Formula-level tests pinned to hand-checked numbers."""

import math

import pytest

from portfolio_risk import metrics as m


def test_wealth_index_starts_at_one():
    assert m.wealth_index([0.10, -0.10]) == pytest.approx([1.0, 1.10, 0.99])


def test_drawdown_series_and_current_drawdown():
    # wealth 1, 1.2, 0.9, 1.08: drawdowns 0, 0, -25%, -10%
    assert m.drawdown_series([0.2, -0.25, 0.2]) == pytest.approx([0, 0, -0.25, -0.10])
    assert m.current_drawdown([0.2, -0.25, 0.2]) == pytest.approx(-0.10)


def test_max_drawdown_tie_is_flagged_and_rule_applied():
    # wealth 1, 0.9, 1.0, 0.9: two equal 10% falls
    early = m.max_drawdown([-0.10, 1 / 9, -0.10], "earliest")
    late = m.max_drawdown([-0.10, 1 / 9, -0.10], "latest")
    assert early.tied and late.tied
    assert (early.trough_index, late.trough_index) == (1, 3)
    assert early.value == pytest.approx(-0.10) and late.value == pytest.approx(-0.10)
    with pytest.raises(ValueError):
        m.max_drawdown([0.01], "middle")


def test_max_drawdown_of_rising_path_is_zero():
    event = m.max_drawdown([0.01, 0.02])
    assert event.value == 0.0 and not event.tied


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0001, True])
def test_invalid_simple_return_rejected(bad):
    with pytest.raises(ValueError, match="INVALID_SIMPLE_RETURN"):
        m.volatility([0.01, bad])


def test_empty_and_single_observation_are_undefined():
    with pytest.raises(m.Undefined) as empty:
        m.cumulative_return([])
    assert empty.value.reason == "NO_OBSERVATIONS"
    with pytest.raises(m.Undefined) as one:
        m.volatility([0.01])
    assert one.value.reason == "SD_REQUIRES_TWO_OBSERVATIONS"


def test_annualisation_factor_is_fixed_not_the_sample_size():
    r = [0.01, -0.005, 0.002, 0.004]
    assert m.volatility(r, 250) == pytest.approx(m.volatility(r, 1) * math.sqrt(250))


def test_downside_with_no_shortfall_is_zero_but_sortino_undefined():
    dd = m.downside_deviation([0.02, 0.03], [0.01, 0.01])
    assert dd.periodic == 0.0 and dd.shortfalls == 0
    with pytest.raises(m.Undefined) as exc:
        m.sortino([0.02, 0.03], [0.01, 0.01])
    assert exc.value.reason == "ZERO_RF_DOWNSIDE"


def test_sharpe_hand_checked():
    # excess 1% and 3%: mean 2%, sample SD 1.4142%, ratio sqrt(2) per period
    assert m.sharpe([0.011, 0.031], [0.001, 0.001], 1) == pytest.approx(math.sqrt(2))
    assert m.sharpe([0.011, 0.031], [0.001, 0.001], 250) == pytest.approx(math.sqrt(2) * math.sqrt(250))


def test_sortino_reconciles_with_downside_deviation():
    r, f = [0.004, -0.006, 0.002, 0.009, -0.001], [0.001] * 5
    dd = m.downside_deviation(r, f, 250)
    mean_excess = sum(a - b for a, b in zip(r, f)) / 5
    assert m.sortino(r, f, 250) == pytest.approx(250 * mean_excess / dd.annualised)


def test_misaligned_series_rejected():
    with pytest.raises(ValueError, match="RF_INTERVAL_ALIGNMENT_FAILED"):
        m.sharpe([0.01, 0.02], [0.001])


def test_historical_var_and_es_k_worst():
    returns = [-(i + 1) / 1000 for i in range(250)]          # -0.1% ... -25%
    # k = ceil(250 * 5%) = 13: the 13th worst day is -23.8%
    assert m.historical_var(returns, 0.95) == pytest.approx(0.238)
    assert m.historical_es(returns, 0.95) == pytest.approx(sum(range(238, 251)) / 13 / 1000)
    assert m.historical_var([0.01] * 20, 0.95) == pytest.approx(-0.01)   # a gain at the tail: negative loss


def test_var_tail_too_small_and_bad_confidence():
    with pytest.raises(ValueError):
        m.historical_var([0.01, 0.02], 1.0)


def test_beta_hand_checked_and_zero_market_variance():
    market = [0.01, -0.01, 0.02]
    assert m.beta([2 * x for x in market], market, [0.0] * 3) == pytest.approx(2.0)
    with pytest.raises(m.Undefined) as exc:
        m.beta([0.01, 0.02], [0.001, 0.001], [0.001, 0.001])
    assert exc.value.reason == "ZERO_MARKET_VARIANCE"
