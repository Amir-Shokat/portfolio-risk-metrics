"""Generate the synthetic example files in examples/ (no real client or market data).

    python scripts/make_example_data.py

* trading_days.csv  every calendar date, open or closed. Sessions run Saturday to Wednesday,
                    as on the Tehran Stock Exchange, minus a synthetic holiday list built from
                    approximate Iranian public holidays. It is not an official calendar.
* daily_returns.csv one made-up portfolio's daily TWR (decimals), with two sessions the upstream
                    service marked not_computed.
* tbill_ytm.csv     made-up annual Treasury-bill YTM quotes in percent, one per session, with one
                    quote deliberately missing in March 2025.
* market_index.csv  a made-up total-index daily return series, for beta.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 7
CAL_START, CAL_END = date(2024, 3, 1), date(2026, 10, 10)
FIRST_RETURN, LAST_RETURN = date(2024, 5, 4), date(2026, 9, 30)
NOT_COMPUTED = {date(2026, 2, 8), date(2026, 2, 9)}
MISSING_RF = {date(2025, 3, 8)}

# Approximate solar-calendar holidays (month, day) and a lunar list for 2024 that moves
# about 11 days earlier each year. Synthetic, for examples only.
SOLAR = [(2, 10), (3, 19), (3, 20), (3, 21), (3, 22), (3, 23), (3, 24), (4, 1), (4, 2), (6, 3), (6, 4)]
LUNAR_2024 = [date(2024, 2, 25), date(2024, 4, 1), date(2024, 4, 10), date(2024, 4, 11), date(2024, 5, 4),
              date(2024, 6, 17), date(2024, 6, 25), date(2024, 7, 15), date(2024, 7, 16), date(2024, 8, 25),
              date(2024, 9, 2), date(2024, 9, 4), date(2024, 9, 12), date(2024, 9, 21), date(2024, 12, 4),
              date(2024, 1, 14), date(2024, 1, 28)]


def holidays() -> set[date]:
    out = set()
    for year in range(2024, 2027):
        out |= {date(year, m, d) for m, d in SOLAR}
        out |= {d.replace(year=year) - timedelta(days=11 * (year - 2024)) for d in LUNAR_2024}
    return out


def main() -> None:
    rng = random.Random(SEED)
    out = Path(__file__).resolve().parents[1] / "examples"
    out.mkdir(exist_ok=True)
    closed_days = holidays()

    calendar, sessions = [], []
    d = CAL_START
    while d <= CAL_END:
        is_open = d.weekday() in (5, 6, 0, 1, 2) and d not in closed_days
        calendar.append((d, "open" if is_open else "closed"))
        if is_open:
            sessions.append(d)
        d += timedelta(days=1)

    # market: slow volatility regimes plus mild autocorrelation (price limits spread news over days)
    market, returns, ytm = {}, {}, {}
    prev_m, vol, rate = 0.0, 0.010, 29.5
    for s in sessions:
        vol = min(0.022, max(0.006, vol * (1 + rng.gauss(0, 0.05))))
        shock = 0.0
        if date(2026, 1, 3) <= s <= date(2026, 2, 4):       # a sell-off
            shock = -0.0060
        elif date(2026, 2, 10) <= s <= date(2026, 4, 30):   # and its recovery
            shock = 0.0035
        elif date(2026, 8, 22) <= s <= date(2026, 9, 16):   # a late dip
            shock = -0.0035
        m = 0.0011 + shock + 0.20 * prev_m + rng.gauss(0, vol)
        m = max(-0.05, min(0.05, m))
        prev_m = m
        market[s] = m
        rate = min(34.0, max(25.0, rate + rng.gauss(0, 0.08)))
        ytm[s] = rate
        if FIRST_RETURN <= s <= LAST_RETURN:
            r = 0.0004 + 0.9 * m + rng.gauss(0, 0.006)
            returns[s] = max(-0.06, min(0.06, r))

    with open(out / "trading_days.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "session"])
        w.writerows((d.isoformat(), flag) for d, flag in calendar)
    with open(out / "daily_returns.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "twr", "status"])
        for s, r in returns.items():
            w.writerow([s.isoformat(), "", "not_computed"] if s in NOT_COMPUTED else [s.isoformat(), f"{r:.6f}", "ok"])
    with open(out / "tbill_ytm.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "ytm_percent"])
        w.writerows((s.isoformat(), f"{q:.2f}") for s, q in ytm.items() if s not in MISSING_RF)
    with open(out / "market_index.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "return"])
        w.writerows((s.isoformat(), f"{r:.6f}") for s, r in market.items())
    print(f"Wrote {len(calendar)} calendar days, {len(returns)} returns and {len(ytm)} quotes to {out}")


if __name__ == "__main__":
    main()
