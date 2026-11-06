# Eligibility and statuses

A risk number on a retail page is only useful if it is honest about when it cannot be
shown. The package never returns a fake 0, infinity or NaN. Every result has a **value**
(or `None`), a **status**, and the full list of **reasons**.

## Rules

1. A value that cannot be shown is `None` plus a status, never 0.
2. Every applicable reason is kept. A Sortino can be both undefined (no shortfall) and short
   of the 30-shortfall gate; both are reported.
3. Input and mathematical problems come before history gates. An undefined ratio is never
   called "not enough history", and missing data is never called a young account.
4. "Not offered for this horizon" is a product rule, not a calculation failure.
5. A value computed below its gate is kept as a **diagnostic** for internal review (CLI
   `--diagnostics`), but is not published.
6. Gates are inclusive: 30 observations pass a 30-observation gate.
7. Counts come only from inside the selected window. A window is never stretched to meet
   a gate, and holidays are never padded with zero returns to reach one.

## History gates (policy `single-gate-v1`, ratios `250obs-v1`)

| Metric | Horizons offered | Minimum |
|---|---|---|
| Cumulative return | 1M 3M 6M 1Y | 1 observation |
| Max / current drawdown, recovery | 1M 3M 6M 1Y | 20 observations |
| Volatility | 1M 3M 6M 1Y | 30 observations |
| Downside deviation | 3M 6M 1Y | 30 observations and 30 shortfalls (`r_t < rf_t`) |
| Sharpe | 1Y | 250 aligned observations |
| Sortino | 1Y | 250 aligned observations and 30 shortfalls |
| Weekly Sharpe / Sortino | all | none approved: `POLICY_PENDING` |
| VaR, ES, beta (extensions) | 6M 1Y | 120 observations |

There is one gate per metric. An earlier draft had "limited" and "standard" quality tiers
(60/120 boundaries); they were removed because two thresholds for one number confused both
users and engineers. There is no elapsed-calendar-day gate for Sharpe and Sortino: 250
observations are enough even if they span fewer than 365 days.

## Statuses, in precedence order

The first matching reason decides the status.

| Status | Reason codes | Meaning for the user |
|---|---|---|
| `NOT_OFFERED` | `NOT_OFFERED_FOR_HORIZON` | this measure is not shown for this period |
| `INVALID_INPUT` | `INVALID_SIMPLE_RETURN`, `RETURN_ON_CLOSED_DAY`, `UNKNOWN_CALENDAR_DATE`, `INVALID_RF_QUOTE`, `INVALID_MARKET_RETURN` | data problem; investigate, do not show |
| `POLICY_PENDING` | `TOTAL_LOSS_POLICY_PENDING`, `WEEKLY_POLICY_PENDING` | a rule needed to show it is not decided yet |
| `INCOMPLETE_COVERAGE` | `MISSING_RETURN` | a session in the window has no return |
| `RF_MISSING` | `MISSING_RF_RETURN` | no risk-free quote for a session; blocks only metrics that read it |
| `MARKET_MISSING` | `MISSING_MARKET_RETURN`, `NO_MARKET_SERIES` | beta cannot be aligned |
| `UNDEFINED` | `ZERO_EXCESS_SD`, `ZERO_RF_DOWNSIDE`, `ZERO_MARKET_VARIANCE` | the formula has a zero denominator |
| `INSUFFICIENT_HISTORY` | `MIN_OBSERVATIONS_NOT_MET`, `NO_OBSERVATIONS`, `SD_REQUIRES_TWO_OBSERVATIONS`, `TAIL_TOO_SMALL` | not enough observations yet |
| `INSUFFICIENT_SHORTFALLS` | `MIN_SHORTFALLS_NOT_MET` | too few days below the risk-free return |
| `NO_DRAWDOWN` | `NO_DRAWDOWN_EVENT` | wealth never fell below its peak (shown as a message) |
| `NOT_RECOVERED` | `NOT_RECOVERED_IN_WINDOW` | shown with the window-specific label |
| `OK` | none, or only informational reasons | shown |

Informational reasons never change the status: `NOT_COMPUTED_SESSIONS_EXCLUDED`,
`TIE_RULE_APPLIED`, `PARTIAL_WEEKS_EXCLUDED`, `EXTENSION_METRIC`, `RATIO_LOOKBACK_LAST_N`.

## Three views of one result

The original specification kept three separate axes. The primary status is the single
summary; the other two are derived:

* **calculation**: `computed`, `insufficient_observations`, `missing_input`,
  `invalid_input`, `undefined`, `policy_pending`
* **publication**: `eligible` (OK, no drawdown, not recovered), `withheld`, `not_offered`

The chart [`status_matrix.png`](status_matrix.png) shows the publication view for every metric
and horizon of the synthetic portfolio.
