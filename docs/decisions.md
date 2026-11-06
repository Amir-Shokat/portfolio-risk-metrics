# Decision log

Decisions made while defining the risk measures, rewritten without internal references.
"Supersedes" means the earlier rule is kept in history but no longer applies.

| # | Date | Decision | Why | Version |
|---|---|---|---|---|
| D1 | 2026-10 (early) | The package takes daily cash-flow-adjusted TWR as input and does not rebuild it | Risk should describe the portfolio, not deposit timing; one owner per number | input contract |
| D2 | 2026-10 (early) | Fixed annualisation factor 250 for volatility, downside, Sharpe and Sortino, regardless of horizon or the user's row count | Users with different histories must be comparable; the factor is a convention, not a sample size | 1.2 |
| D3 | 2026-10 (early) | Risk-free return from Treasury-bill YTM: `(1 + YTM) ** (1/250) - 1` per session; no calendar-day accrual | Matches the factor in D2; an ACT/365 draft gave a Monday three days of interest | 1.2 |
| D4 | 2026-10 (early) | Missing returns block the window; `not_computed` sessions are excluded and reported; holidays are not padded | A zero is a claim about the portfolio; silence about a gap hides risk | input contract |
| D5 | 2026-10-25 | Recovery is searched only inside the selected window; later data cannot rewrite a past window | A past period's answer must be stable; otherwise support cannot explain a screenshot | recovery 1.0 |
| D6 | 2026-10-25 | Sharpe and Sortino need 250 aligned observations; the 365-elapsed-day condition is removed | The day count added nothing once observations were counted, and blocked active users | 250obs-v1 |
| D7 | 2026-10-25 | One history gate per metric (MDD 20, volatility 30, downside 30 + 30 shortfalls, ratios 250); "limited/standard" quality tiers removed | Two thresholds for one number confused users and engineers | single-gate-v1 |
| D8 | 2026-10-26 | Recovery duration = official sessions in `(trough, recovery]` | Removes off-by-one disputes; holidays never lengthen recovery | recovery 1.1 |
| D9 | 2026-10-27 | Downside target changes from 0 to the same session's risk-free return; N stays all aligned observations; shortfall gate counts `r_t < rf_t` | A positive return below the risk-free rate is still a shortfall for an investor who could hold T-bills; supersedes the zero target | methodology 1.3, rf-target-v1 |
| D10 | 2026-10-27 | Weekly Sharpe and Sortino added alongside daily ones, `sqrt(52)`, weekly rf compounds daily rf | Daily ratios on a price-limited market are noisy; weekly is a cross-check. Week boundary and weekly minimum history are not approved, so publication is pending | weekly-ratios-v1 |
| D11 | this repo | VaR, ES and beta are extensions with their own version | They were part of the method research but not the approved first-release set | toolkit-ext-v1 |
| D12 | this repo | Ratio lookback is configurable (`window` or `last_n`) | Makes the "12 months vs 250 sessions" conflict visible and testable instead of hidden | contract option |

## What each decision changed downstream

Every change followed the order in [change-process.md](change-process.md): decision log,
formula definitions, methodology version, contract JSON, independent reference calculation,
acceptance scenarios, developer package, then user-facing text. D9 for example changed the
contract, the reference calculations, the shortfall gate, the Sortino denominator and the
acceptance scenarios together, and required recalculation under a new version while keeping
earlier published results.
