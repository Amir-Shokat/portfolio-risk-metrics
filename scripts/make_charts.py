"""Draw the PNG charts in docs/ from the synthetic examples.

    pip install -e ".[charts]"
    python scripts/make_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from portfolio_risk import METRICS, assess, load_contract, load_inputs  # noqa: E402
from portfolio_risk.metrics import drawdown_series, wealth_index  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EX, DOCS = ROOT / "examples", ROOT / "docs"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
GOOD, SERIOUS, NEUTRAL = "#0ca30c", "#ec835a", "#d9d8d3"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "font.size": 9,
})


def load():
    return load_inputs(EX / "daily_returns.csv", EX / "trading_days.csv", EX / "tbill_ytm.csv",
                       EX / "market_index.csv")


def drawdown_chart(inputs) -> None:
    report = assess(inputs, "1Y")
    w = report.window
    dates, wealth, dd = w.point_dates, wealth_index(w.returns), drawdown_series(w.returns)
    rec = report["recovery_sessions"]
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(8, 5), sharex=True, height_ratios=[3, 2])
    top.plot(dates, wealth, color=BLUE, linewidth=1.6)
    top.set_ylabel("wealth (start = 1.0)")
    top.set_title("One-year window: wealth, maximum drawdown and its recovery", loc="left", fontsize=10)
    marks = [("peak", rec.details["peak_date"]), ("trough", rec.details["trough_date"]),
             ("recovered", rec.details["recovery_date"])]
    for label, d in marks:
        i = dates.index(d)
        top.plot([d], [wealth[i]], "o", color=INK, markersize=5, zorder=3)
        top.annotate(label, (d, wealth[i]), xytext=(4, 6 if label != "trough" else -12),
                     textcoords="offset points", color=MUTED)
    bottom.fill_between(dates, dd, 0, color=ORANGE, alpha=0.35, linewidth=0)
    bottom.plot(dates, dd, color=ORANGE, linewidth=1.2)
    bottom.set_ylabel("drawdown")
    bottom.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    t, r = rec.details["trough_date"], rec.details["recovery_date"]
    bottom.annotate(f"max drawdown {report['max_drawdown'].value:.1%}; recovered after "
                    f"{int(rec.value)} sessions", (t, report["max_drawdown"].value),
                    xytext=(10, -2), textcoords="offset points", color=INK)
    bottom.axvspan(t, r, color=GRID, alpha=0.5, linewidth=0)
    fig.text(0.01, 0.01, "Synthetic data. Recovery is counted in official sessions in (trough, recovery].",
             color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(DOCS / "drawdown_recovery.png", dpi=130)
    plt.close(fig)


def status_chart(inputs) -> None:
    contract = load_contract()
    horizons = list(contract.horizons)
    reports = {h: assess(inputs, h) for h in horizons}
    colour = {"eligible": GOOD, "withheld": SERIOUS, "not_offered": NEUTRAL}
    fig, ax = plt.subplots(figsize=(8, 5.2))
    for x, h in enumerate(horizons):
        for y, metric in enumerate(METRICS):
            res = reports[h][metric]
            ax.add_patch(plt.Rectangle((x + 0.03, y + 0.06), 0.94, 0.88, color=colour[res.publication],
                                       alpha=0.35 if res.publication != "not_offered" else 0.6, linewidth=0))
            ax.text(x + 0.5, y + 0.5, res.status.value.replace("_", " ").lower(), ha="center",
                    va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, len(horizons))
    ax.set_ylim(len(METRICS), 0)
    ax.set_xticks([i + 0.5 for i in range(len(horizons))], horizons)
    ax.set_yticks([i + 0.5 for i in range(len(METRICS))], METRICS)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.xaxis.tick_top()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.5) for c in colour.values()]
    ax.legend(handles, ["shown", "withheld (status explains why)", "not offered for this horizon"],
              loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3, frameon=False)
    ax.set_title("What the page may show, by metric and horizon (synthetic portfolio)", loc="left",
                 fontsize=10, pad=24)
    fig.tight_layout()
    fig.savefig(DOCS / "status_matrix.png", dpi=130)
    plt.close(fig)


def target_chart(inputs) -> None:
    w = assess(inputs, "1Y").window
    below_zero = sum(r < 0 for r in w.returns)
    positive_below_rf = sum(0 <= r < f for r, f in zip(w.returns, w.rf))
    above = len(w.returns) - below_zero - positive_below_rf
    fig, ax = plt.subplots(figsize=(8, 3.0))
    rows = [("zero target (old draft)", [(below_zero, ORANGE, "below 0")]),
            ("risk-free target (v1.3)", [(below_zero, ORANGE, "below 0"),
                                         (positive_below_rf, BLUE, "0 or more, but below risk-free")])]
    for y, (label, parts) in enumerate(rows):
        left = 0
        for value, col, _ in parts:
            ax.barh(y, value, left=left, color=col, height=0.5, edgecolor=SURFACE, linewidth=2)
            left += value
        ax.text(left + 2, y, f"{left} shortfalls", va="center", color=INK)
    ax.set_yticks([0, 1], [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, len(w.returns))
    ax.set_xlabel(f"sessions in the one-year window (N = {len(w.returns)}, the divisor in both cases; "
                  f"{above} at or above risk-free)")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in (ORANGE, BLUE)],
              ["return below 0", "return 0 or more, but below the risk-free return"],
              loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Downside target: which days count as shortfalls", loc="left", fontsize=10)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(DOCS / "downside_target.png", dpi=130)
    plt.close(fig)


def main() -> None:
    inputs = load()
    drawdown_chart(inputs)
    status_chart(inputs)
    target_chart(inputs)
    print(f"Wrote 3 charts to {DOCS}")


if __name__ == "__main__":
    main()
