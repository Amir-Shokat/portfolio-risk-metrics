# Change process

Risk numbers can influence retail users' decisions. A change of method must be deliberate,
visible in the output, and reversible for audit.

## Before changing anything

1. Add an entry to the [decision log](decisions.md): reason, evidence, affected metrics.
2. Say whether it is a **methodology change** (results or meaning can change) or an
   **implementation-only change** (same results).
3. Use the change-impact map to list affected outputs:

```python
from portfolio_risk import load_contract
from portfolio_risk.versioning import impacted_metrics
old = load_contract()
impacted_metrics(old, old.with_changes({"annualization.daily": 240}))
# {'volatility', 'downside_deviation', 'sharpe', 'sortino'}
```

## Approval gate

* Product approves scope, user meaning, visibility and wording intent.
* Finance / risk approves the financial definitions.
* Data / engineering confirms source availability, timing, versioning and failure behaviour.
* QA approves test evidence and expected results.
* Legal / compliance reviews claims where required.

A role listed as reviewer is not evidence of approval. Record who approved and when.

## Update order

1. Decision log.
2. Formula definitions ([methodology.md](methodology.md)).
3. Methodology version, when results or meaning can change.
4. Machine-readable contract (`methodology.json`).
5. Independent reference calculation and worked examples (tests pinned to hand-checked numbers).
6. Acceptance scenarios and reason codes ([features](features/)).
7. Developer package.
8. User-facing text.

## Results after a change

* A result's identity (`versioning.ResultKey`) includes the methodology version, the
  fingerprint of only the contract sections the metric depends on, and the revisions of the
  inputs it read. Changing the drawdown gate does not invalidate cached Sharpe ratios; a
  corrected risk-free series does not invalidate volatility.
* Recalculated results get new keys. Stale cache entries are never served as fresh.
* Earlier published results are kept and marked superseded, for audit and customer support.
* Re-publishing the same identity is a no-op, so a replayed job cannot create duplicates.

## Release checklist

- [ ] The input boundary is explicit.
- [ ] Every open decision has an owner and a stated consequence.
- [ ] Formula, unit, target, denominator, annualisation and sign are explicit.
- [ ] Missing, invalid, undefined, pending and insufficient-history states are distinct.
- [ ] Changed formulas have independently calculated examples.
- [ ] Boundary and edge-case scenarios pass.
- [ ] Calendar, risk-free and TWR dependencies have versions and failure behaviour.
- [ ] Old results are reproducible; correction and recalculation rules are agreed.
- [ ] User-facing text does not imply investment advice, safety or forecast certainty.

If any item is incomplete, the methodology stays "under review" and is not described as
approved or production-ready.
