# Acceptance criteria

The behaviour a release must show, written as checkable statements. Each line maps to a
Gherkin scenario in [features/](features/) and to a test in `tests/test_features.py`
(the last test there fails if a scenario has no mirror).

## Calculation

- AC1 Returns are linked: +10% then -10% gives -1%.
- AC2 The opening wealth point is part of the drawdown path.
- AC3 Volatility uses the sample standard deviation (N - 1) times sqrt(250).
- AC4 Downside deviation uses the same session's risk-free return as target and divides by
  all aligned observations; equality with the risk-free return is not a shortfall.
- AC5 The Sharpe denominator is the standard deviation of excess returns.
- AC6 Sortino and downside deviation share target, dates and N.
- AC7 Zero denominators give `UNDEFINED`, never 0 or infinity.

## Data

- AC8 A missing session blocks the window (`INCOMPLETE_COVERAGE`); it is never filled with 0.
- AC9 A genuine zero return is a valid observation.
- AC10 `not_computed` sessions are excluded, counted and reported, and do not change the status.
- AC11 A missing risk-free quote blocks only the metrics that read the risk-free series.
- AC12 A return on a closed or unknown calendar day is `INVALID_INPUT`.
- AC13 A -100% return is `POLICY_PENDING`; below -100% is `INVALID_INPUT`.

## Eligibility

- AC14 Gates are inclusive (29 observations fail a 30 gate, 30 pass).
- AC15 Sharpe and Sortino need 250 aligned observations and no elapsed-day condition.
- AC16 Values below a gate are kept as diagnostics and not published.
- AC17 Metrics outside their horizons are `NOT_OFFERED`.
- AC18 All applicable reasons are reported; precedence picks the primary status.

## Recovery

- AC19 Duration counts official sessions in `(trough, recovery]`; holidays are not counted.
- AC20 The search stops at the window end; a past window keeps "not recovered by the end of
  this period".
- AC21 No drawdown and not recovered are messages, not zero.
- AC22 Missing coverage is not reported as not recovered.

## Weekly ratios

- AC23 Weekly rf compounds daily rf; it is not `(1 + YTM) ** (1/52) - 1`.
- AC24 Weekly excess is `R_w - F_w`; daily excess returns are not compounded.
- AC25 sqrt(52) is a scaling factor, not a minimum history.
- AC26 Weekly ratios stay `POLICY_PENDING` until the week policy is approved.

## Change control

- AC27 Every report shows the methodology version, policy versions and contract fingerprint.
- AC28 A rule change invalidates only dependent metrics.
- AC29 An input correction changes the keys of dependent results only.
- AC30 Published results are superseded, never overwritten; replays are idempotent.

## Out of scope for this package

Computing TWR itself, the screen design, explanatory copy for users, and production
monitoring. Those were separate work streams with their own specifications.
