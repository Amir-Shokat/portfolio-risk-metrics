# Methodology (version 1.3)

This page defines every number the package produces. The machine-readable version is
[`src/portfolio_risk/methodology.json`](../src/portfolio_risk/methodology.json); the code reads
its rules from there and prints the version it used.

## Input boundary

The package starts from a **daily, cash-flow-adjusted, simple time-weighted return (TWR)**
for each official market session. It does not rebuild returns from trades, balances or
deposits; that is the job of the upstream return service. TWR removes the effect of the
investor's own deposits and withdrawals, so risk measures describe the portfolio, not the
timing of cash flows.

Notation: `r_t` is the decimal return of session `t` (0.012 = 1.2%), `rf_t` the risk-free
return of the same session, `x_t = r_t - rf_t` the excess return, `N` the number of valid
aligned observations inside the selected window, `A = 250` the daily annualisation factor.

## Risk-free return

The input quotes the risk-free rate as the annual yield to maturity (YTM) of government
Treasury bills. Each session gets

```
rf_t = (1 + YTM_t) ** (1 / 250) - 1
```

* 250 is a fixed number of periods per year, the same as the volatility factor. It is not
  the number of calendar days.
* One value per session. A Monday after a two-day closure gets one session of
  risk-free return, not three calendar days (an earlier ACT/365 draft did this).
* The quote of the same session is used. A missing quote is never replaced by zero, by
  yesterday's quote or by today's rate (see [data-and-calendar.md](data-and-calendar.md)).
* The unit must be declared (`ytm` decimal or `ytm_percent`). `1.0` could be 1% or 100%,
  so the size of the number is never used to guess.

## Path measures

| Measure | Formula | Notes |
|---|---|---|
| Wealth index | `W_0 = 1`, `W_t = W_(t-1) (1 + r_t)` | `W_0` sits on the window's opening boundary |
| Cumulative return | `W_N - 1` | linked, never summed: +10% then -10% is -1% |
| Drawdown | `D_t = W_t / max(W_0..W_t) - 1` | `D_0 = 0`; a fall on the first day is a drawdown |
| Maximum drawdown | `min(D_t)` | signed, <= 0; ties are flagged `TIE_RULE_APPLIED` |
| Current drawdown | `D_N` | against the highest point of the same window |

## Recovery (policy `1.1-window-bound-session-count`)

* The event is the maximum drawdown of the selected window.
* Recovery is the first wealth point after the trough at or above the reference peak.
* The search ends at the window end, inclusive. Later data never changes a past window.
* Duration = official sessions in `(trough_date, recovery_date]`: the trough session is not
  counted, the recovery session is. Holidays do not count; a session on which the investor
  did not trade does count. The official calendar decides, not the user's row count.
* "Not recovered" and "no drawdown" have no number. Neither is shown as zero. The label
  depends on the window: *not recovered by the end of this period* (past window) or
  *not recovered as of the latest data* (current window).

## Dispersion and ratios (daily)

| Measure | Formula |
|---|---|
| Volatility | `sample_sd(r) * sqrt(250)` (divisor `N - 1`) |
| Downside deviation | `sqrt(sum(min(x_t, 0)^2) / N) * sqrt(250)` |
| Shortfall count | `count(r_t < rf_t)`; equality is not a shortfall |
| Sharpe | `mean(x) / sample_sd(x) * sqrt(250)` |
| Sortino | `mean(x) / sqrt(sum(min(x_t, 0)^2) / N) * sqrt(250)` |

Points that matter:

* **The downside target is the risk-free return of the same session**, not zero. A day
  with +0.05% when the risk-free return is 0.10% is a shortfall. The chart
  [`downside_target.png`](downside_target.png) shows how many extra days this adds.
* **The divisor of downside deviation is N, every aligned observation**, not only the
  shortfall days. Dividing by the shortfall count overstates downside risk.
* **The Sharpe denominator is the SD of excess returns.** With a changing risk-free rate
  it differs from the SD of raw returns.
* Downside deviation and Sortino share target, dates and N, so
  `Sortino = 250 * mean(x) / annualised_downside` holds exactly and is used as a
  reconciliation check.
* The factor is fixed. It is not the user's number of observations and not the actual
  number of sessions in a year. No adjustment for serial correlation is applied; daily
  market microstructure can spread news over several days, so short-horizon volatility may
  be understated. This is recorded as a known limitation, not hidden.

## Weekly ratios (policy `weekly-ratios-v1`, publication pending)

```
R_w = prod(1 + r_t) - 1         over the week's valid sessions
F_w = prod(1 + rf_t) - 1        over exactly the same sessions
x_w = R_w - F_w                 daily excess returns are not compounded
Sharpe_w  = mean(x_w) / sample_sd(x_w) * sqrt(52)
Sortino_w = mean(x_w) / sqrt(sum(min(x_w, 0)^2) / N_w) * sqrt(52)
```

`F_w` compounds the daily values; it is not `(1 + YTM) ** (1/52) - 1`. 52 is a scaling
factor, not a minimum number of weeks. The week boundary, partial weeks at the edges and the
minimum history are open decisions, so these ratios are computed as diagnostics and
published as `POLICY_PENDING`. The code uses a Monday-to-Sunday week as an example only.

## Extensions (not in the approved first-release set)

| Measure | Convention |
|---|---|
| Historical VaR 95% | one session, positive number = loss; the k-th worst return, `k = ceil(N * 5%)`, no interpolation (250 returns: the 13th worst) |
| Expected shortfall 95% | average of the same k worst returns |
| Beta | `cov(r - rf, m - rf) / var(m - rf)` against a total-market index, exact session alignment |

They carry the informational reason `EXTENSION_METRIC` and have their own version
(`toolkit-ext-v1`), so they can change without touching the core methodology.

## Windows

Horizons 1M, 3M, 6M and 1Y are trailing calendar windows: official sessions in
`(as_of - N months, as_of]`, with month-end clamping (31 March minus one month is 28 or 29
February). If the account started inside the window, the sessions before the first return
are reported as "before first return" and are not treated as missing.

Daily Sharpe and Sortino use the selected window by default. Because a market with about 240
sessions a year cannot reach 250 observations in 12 months, the contract also supports
`ratio_lookback = "last_n"`: the latest 250 valid sessions. Which one the product uses is an
open decision ([open-questions.md](open-questions.md)).
