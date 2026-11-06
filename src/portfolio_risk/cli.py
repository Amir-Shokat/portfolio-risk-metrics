"""Command line: ``portfolio-risk --returns ... --rf ... --calendar ... --horizon 1Y``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .contract import load_contract
from .inputs import InputError, load_inputs
from .report import RiskReport, assess


def _fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "decimal":
        return f"{value * 100:.2f}%"
    if unit == "sessions":
        return f"{int(value)}"
    return f"{value:.2f}"


def render(report: RiskReport, diagnostics: bool = False) -> str:
    h = report.header()
    c = h["coverage"]
    lines = [
        f"Portfolio risk report  |  methodology {h['methodology_version']}  |  contract {h['contract_fingerprint']}",
        "policies: " + "  ".join(f"{k}={v}" for k, v in h["policy_versions"].items()),
        f"horizon {h['horizon']}: sessions after {h['window_opening']} up to {h['window_end']}"
        + ("  (current window)" if h["current_window"] else "  (historical window)"),
        f"official sessions {c['official_sessions']}  valid {c['valid_observations']}  "
        f"not computed {c['not_computed']}  missing {c['missing']}  rf aligned {c['rf_aligned']}"
        + (f"  before first return {c['sessions_before_first_return']}" if c["sessions_before_first_return"] else ""),
        "",
    ]
    head = f"{'metric':<20}{'value':>10}  {'status':<24}{'n':>5}{'short':>7}  reasons"
    if diagnostics:
        head = f"{'metric':<20}{'value':>10}{'diagnostic':>12}  {'status':<24}{'n':>5}{'short':>7}  reasons"
    lines += [head, "-" * len(head)]
    for r in report.results.values():
        shown = [x for x in r.reasons if x not in ("NOT_COMPUTED_SESSIONS_EXCLUDED",)]
        note = ", ".join(shown)
        if r.status.value == "NOT_RECOVERED" and "label" in r.details:
            note = r.details["label"]
        short = "" if r.shortfalls is None else str(r.shortfalls)
        diag = f"{_fmt_value(r.diagnostic, r.unit):>12}" if diagnostics else ""
        lines.append(f"{r.metric:<20}{_fmt_value(r.value, r.unit):>10}{diag}  {r.status.value:<24}"
                     f"{r.n:>5}{short:>7}  {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portfolio-risk", description=__doc__)
    parser.add_argument("--returns", required=True, help="daily TWR CSV: date,twr,status")
    parser.add_argument("--rf", required=True, help="Treasury-bill YTM CSV: date,ytm or date,ytm_percent")
    parser.add_argument("--calendar", required=True, help="official calendar CSV: date,session")
    parser.add_argument("--market", help="optional market index return CSV: date,return (for beta)")
    parser.add_argument("--horizon", default="1Y", help="1M, 3M, 6M, 1Y or ALL (default 1Y)")
    parser.add_argument("--as-of", type=date.fromisoformat, help="window end date (default: last return)")
    parser.add_argument("--ratio-lookback", choices=["window", "last_n"],
                        help="daily Sharpe/Sortino sample: the selected window (default) or the last 250 valid sessions")
    parser.add_argument("--contract", help="alternative methodology JSON")
    parser.add_argument("--diagnostics", action="store_true", help="also show values withheld by a gate")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)

    try:
        inputs = load_inputs(args.returns, args.calendar, args.rf, args.market)
    except (InputError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    contract = load_contract(args.contract)
    horizons = list(contract.horizons) if args.horizon.upper() == "ALL" else [args.horizon.upper()]
    reports = [assess(inputs, h, args.as_of, contract, args.ratio_lookback) for h in horizons]
    if args.json:
        payload = [r.to_dict(args.diagnostics) for r in reports]
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2))
    else:
        print("\n\n".join(render(r, args.diagnostics) for r in reports))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
