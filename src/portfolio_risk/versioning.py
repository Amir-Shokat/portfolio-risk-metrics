"""Result identity, cache invalidation and the change-impact map.

A published number must be reproducible later, and a correction must not quietly
overwrite what users already saw. Three rules from the original change process:

1. A result's identity includes the methodology version, the parts of the contract the
   metric depends on, and the revisions of the inputs it read (TWR, calendar, and for
   some metrics the risk-free and market series).
2. When an input is corrected (new revision) or the methodology changes, every dependent
   result gets a new key, so stale cache entries are never served as fresh. A risk-free
   correction does not invalidate volatility, which never reads the risk-free series.
3. Earlier published results are kept, marked superseded, for audit and customer support.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .contract import MARKET_METRICS, METRICS, RF_METRICS, Contract


def impacted_metrics(old: Contract, new: Contract) -> set[str]:
    """Metrics whose definition differs between two contracts (the change-impact map)."""
    return {metric for metric in METRICS if old.metric_fingerprint(metric) != new.metric_fingerprint(metric)}


def input_dependencies(metric: str) -> tuple[str, ...]:
    """Which input revisions a metric reads."""
    deps = ["twr", "calendar"]
    if metric in RF_METRICS:
        deps.append("rf")
    if metric in MARKET_METRICS:
        deps.append("market")
    return tuple(deps)


@dataclass(frozen=True)
class ResultKey:
    portfolio: str
    metric: str
    horizon: str
    as_of: date
    methodology_version: str
    metric_fingerprint: str
    input_revisions: tuple[tuple[str, str], ...]

    @classmethod
    def build(cls, portfolio: str, metric: str, horizon: str, as_of: date, contract: Contract,
              revisions: dict[str, str]) -> "ResultKey":
        deps = input_dependencies(metric)
        missing = [d for d in deps if d not in revisions]
        if missing:
            raise ValueError(f"input revisions required for {metric}: {missing}")
        return cls(portfolio, metric, horizon, as_of, contract.methodology_version,
                   contract.metric_fingerprint(metric), tuple((d, revisions[d]) for d in deps))

    @property
    def slot(self) -> tuple[str, str, str, date]:
        """What the user sees: one portfolio, metric, horizon and date."""
        return (self.portfolio, self.metric, self.horizon, self.as_of)

    def digest(self) -> str:
        payload = json.dumps([*map(str, self.slot), self.methodology_version, self.metric_fingerprint,
                              list(self.input_revisions)], separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class StoredResult:
    key: ResultKey
    payload: dict[str, Any]
    superseded_by: str | None = None


@dataclass
class ResultStore:
    """In-memory store that keeps every published version (a model of the required behaviour)."""

    _by_digest: dict[str, StoredResult] = field(default_factory=dict)
    _current: dict[tuple, str] = field(default_factory=dict)

    def get(self, key: ResultKey) -> dict[str, Any] | None:
        """Cache lookup by full identity; a key built from new revisions misses."""
        hit = self._by_digest.get(key.digest())
        return hit.payload if hit else None

    def publish(self, key: ResultKey, payload: dict[str, Any]) -> bool:
        """Store a result. Re-publishing the same identity is a no-op (idempotent replay).

        Returns True when a new version was stored.
        """
        digest = key.digest()
        if digest in self._by_digest:
            return False
        previous = self._current.get(key.slot)
        if previous is not None:
            self._by_digest[previous].superseded_by = digest
        self._by_digest[digest] = StoredResult(key, dict(payload))
        self._current[key.slot] = digest
        return True

    def current(self, slot: tuple) -> dict[str, Any] | None:
        digest = self._current.get(slot)
        return self._by_digest[digest].payload if digest else None

    def history(self, slot: tuple) -> list[StoredResult]:
        """Every version ever published for a slot, oldest first."""
        return [r for r in self._by_digest.values() if r.key.slot == slot]

    def stale(self, slot: tuple, contract: Contract, revisions: dict[str, str]) -> bool:
        """True if the current result for ``slot`` was built from other inputs or rules."""
        digest = self._current.get(slot)
        if digest is None:
            return True
        portfolio, metric, horizon, as_of = slot
        return ResultKey.build(portfolio, metric, horizon, as_of, contract, revisions).digest() != digest
