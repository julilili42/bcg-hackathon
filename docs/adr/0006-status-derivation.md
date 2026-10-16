# ADR 0006 — Status derived from weighted reports with decay, not last-write-wins

**Status:** accepted, 2026-10-16

## Context
Crowd reports conflict and age. Last-write-wins lets one wrong call flip a point and hides uncertainty
from coordinators. The team wants a trust story (O8).

## Decision
Status is never written directly. Each report gets `weight = channel_weight × 0.5^(age_days/half_life)`
(half-life 7 days for live reports, 365 for imported baselines; channel weights voice 1.0, sms 1.0,
web 1.2, import 0.4). Per entity, sum weights per claimed status over 90 days; leader wins;
`confidence = leader/total × min(1, total/2)`; `disputed` when the runner-up is within 25 % and
total ≥ 1.5; `unknown` when total < 0.3. Parameters live in one settings block owned by the Data & Trust
Steward. Implementation is pure functions in `api/core/status.py` with unit and property tests.

## Consequences
- The map can show confidence, "disputed", and "unverified" honestly.
- Recomputation is cheap (per entity on each new report); no background job needed.
- Demo step 5 (conflict) is a direct consequence of this design.
