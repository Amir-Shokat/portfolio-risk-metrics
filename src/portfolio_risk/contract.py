"""The versioned methodology contract.

Every number this package produces depends on choices that a product team can change:
the annualisation factor, the downside target, the minimum history, the recovery rule.
Those choices live in one JSON document (``methodology.json``), not in the code. The code
reads it, applies it and reports which version it used, so any change of policy is
visible in the output and traceable to a new version.

Two fingerprints are provided:

* :meth:`Contract.fingerprint` hashes the whole document.
* :meth:`Contract.metric_fingerprint` hashes only the sections a given metric depends on.
  It is the basis of cache keys and of the change-impact map in :mod:`portfolio_risk.versioning`:
  changing the drawdown gate must not invalidate cached Sharpe ratios.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

#: Metrics in the order they are reported.
METRICS: tuple[str, ...] = (
    "cumulative_twr",
    "max_drawdown",
    "current_drawdown",
    "recovery_sessions",
    "volatility",
    "downside_deviation",
    "sharpe",
    "sortino",
    "sharpe_weekly",
    "sortino_weekly",
    "var_95",
    "es_95",
    "beta",
)

RF_METRICS = frozenset({"downside_deviation", "sharpe", "sortino", "sharpe_weekly", "sortino_weekly", "beta"})
MARKET_METRICS = frozenset({"beta"})
PATH_METRICS = frozenset({"cumulative_twr", "max_drawdown", "current_drawdown", "recovery_sessions"})

#: Contract sections each metric depends on (dotted paths into the JSON document).
#: ``inputs``, ``horizons`` and ``window_rule`` affect every metric.
_COMMON = ("methodology_version", "inputs", "horizons", "window_rule")
DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "cumulative_twr": ("metrics.cumulative_twr",),
    "max_drawdown": ("metrics.max_drawdown", "policies.history"),
    "current_drawdown": ("metrics.current_drawdown", "policies.history"),
    "recovery_sessions": ("metrics.recovery_sessions", "metrics.max_drawdown", "policies.history", "policies.recovery"),
    "volatility": ("metrics.volatility", "policies.history", "annualization.daily"),
    "downside_deviation": ("metrics.downside_deviation", "policies.history", "policies.downside",
                           "annualization.daily", "risk_free"),
    "sharpe": ("metrics.sharpe", "policies.ratio_history", "annualization.daily", "risk_free", "ratio_lookback"),
    "sortino": ("metrics.sortino", "policies.ratio_history", "policies.downside", "annualization.daily",
                "risk_free", "ratio_lookback"),
    "sharpe_weekly": ("metrics.sharpe_weekly", "policies.weekly", "annualization.weekly", "risk_free"),
    "sortino_weekly": ("metrics.sortino_weekly", "policies.weekly", "annualization.weekly", "risk_free"),
    "var_95": ("metrics.var_95", "extensions.var"),
    "es_95": ("metrics.es_95", "extensions.var"),
    "beta": ("metrics.beta", "extensions.beta", "risk_free"),
}


def _get(document: dict, dotted: str) -> Any:
    node: Any = document
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _digest(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Contract:
    """A loaded methodology contract. Treat it as read-only."""

    document: dict = field(repr=False)

    # -- identity -------------------------------------------------------------------------
    @property
    def methodology_version(self) -> str:
        return str(self.document["methodology_version"])

    @property
    def policy_versions(self) -> dict[str, str]:
        policies = self.document.get("policies", {})
        versions = {name: str(p["version"]) for name, p in policies.items() if "version" in p}
        if "extensions" in self.document:
            versions["extensions"] = str(self.document["extensions"]["version"])
        return versions

    def fingerprint(self) -> str:
        """Short hash of the whole document."""
        return _digest(self.document)

    def metric_fingerprint(self, metric: str) -> str:
        """Hash of only the sections that ``metric`` depends on."""
        paths = _COMMON + DEPENDENCIES[metric]
        return _digest({path: _get(self.document, path) for path in paths})

    # -- convenient accessors ---------------------------------------------------------------
    def rule(self, metric: str) -> dict:
        return self.document["metrics"][metric]

    def offered(self, metric: str, horizon: str) -> bool:
        return horizon in self.rule(metric)["horizons"]

    @property
    def daily_factor(self) -> int:
        return int(self.document["annualization"]["daily"])

    @property
    def weekly_factor(self) -> int:
        return int(self.document["annualization"]["weekly"])

    @property
    def rf_periods_per_year(self) -> int:
        return int(self.document["risk_free"]["periods_per_year"])

    @property
    def horizons(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.document["horizons"].items()}

    @property
    def ratio_min_obs(self) -> int:
        return int(self.document["policies"]["ratio_history"]["min_aligned_observations"])

    @property
    def recovery_tie_rule(self) -> str:
        return str(self.document["policies"]["recovery"]["tie_rule"])

    @property
    def not_computed_policy(self) -> str:
        return str(self.document["inputs"]["not_computed_sessions"])

    @property
    def var_confidence(self) -> float:
        return float(self.document["extensions"]["var"]["confidence"])

    def with_changes(self, changes: dict[str, Any]) -> "Contract":
        """Return a new contract with dotted-path values replaced.

        Used to model a proposed policy change and see which metrics it touches.
        """
        document = copy.deepcopy(self.document)
        for dotted, value in changes.items():
            parts = dotted.split(".")
            node = document
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        return Contract(document)


def load_contract(path: str | Path | None = None) -> Contract:
    """Load the packaged contract, or an alternative JSON file."""
    if path is None:
        text = resources.files("portfolio_risk").joinpath("methodology.json").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    document = json.loads(text)
    missing = [key for key in ("methodology_version", "metrics", "policies", "annualization", "risk_free")
               if key not in document]
    if missing:
        raise ValueError(f"contract is missing required sections: {missing}")
    unknown = set(document["metrics"]) - set(METRICS)
    if unknown:
        raise ValueError(f"contract names metrics this package does not implement: {sorted(unknown)}")
    return Contract(document)
