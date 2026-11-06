# Open questions

Decisions that were deliberately **not** made by engineering. Each has a safe default in the
code, so nothing is invented silently, and a consequence if it stays open.

| # | Question | Safe default here | Consequence while open |
|---|---|---|---|
| Q1 | How does a 12-month window meet a 250-observation ratio gate in a market with about 240 sessions a year? | `ratio_lookback = "window"`; `last_n` available | With the window rule, 1Y Sharpe and Sortino are almost never shown (see the example output) |
| Q2 | Which official calendar source, cutoff time and exact window boundary rule? | calendar file is the only source; windows are `(as_of - N months, as_of]` | Session counts can differ by one at the boundaries between systems |
| Q3 | Risk-free source field, unit, effective dating, gaps and revisions | unit must be declared; exact date match; gaps block | A vendor change can silently shift every ratio if not versioned |
| Q4 | Tie-break between equal maximum drawdowns and repeated troughs | earliest trough, flagged `TIE_RULE_APPLIED` | Recovery duration can differ between implementations |
| Q5 | Total loss, full exit and re-funding of an account (capital episodes) | -100% is `POLICY_PENDING`; one series = one episode | Risk after a restart mixes two different investments |
| Q6 | A materiality rule for tiny but non-zero denominators | only exact zero is undefined | A nearly flat portfolio can show an extreme ratio |
| Q7 | Quality thresholds for stale prices, runs of zero returns and extreme returns | extreme values kept and reported | Illiquid holdings make volatility look low |
| Q8 | Official week definition, partial weeks and minimum weekly history | Saturday-to-Friday example, partial weeks excluded, `POLICY_PENDING` | Weekly ratios cannot be published |
| Q9 | Drawdown display sign and precision | stored signed (<= 0), decimals | Front-end and API may round or sign differently |
| Q10 | Adjustment for serial correlation caused by daily price limits | none, documented | Short-horizon volatility is understated |
