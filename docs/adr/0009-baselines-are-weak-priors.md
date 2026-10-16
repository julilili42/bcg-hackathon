# ADR 0009 — Imported and demo baselines are weak priors that one live report overrides

**Status:** accepted, 2026-10-16 (refines ADR 0006)

## Context
With full-weight baselines, the first live report produced "disputed" instead of flipping the status,
which breaks both the demo script and the intuition that a fresh phone call beats a 2009 survey.

## Decision
Each report stores its own weight and `derive_status` uses it (channel weight is the fallback).
Baselines are weak: WPDx and HFR imports weight 0.4 (decaying to a floor of 0.15), demo overlay
baselines weight 0.25 (channel `import`, dated at seed time, so they stay out of the live feed).
A dispute is judged on live reports only (two people disagreeing); priors never create or prevent one. Live
reports weigh 1.0 (voice, SMS) or 1.2 (web). Consequences for the demo numbers:

| Situation | Result |
|---|---|
| Baseline only | status shown, confidence 0.2, "unverified" |
| One live report against the baseline | live status wins, confidence about 0.65, "verified" |
| Two live reports that disagree | `disputed` |
| Third live report | majority wins, confidence about 0.6 |
| A verified point (two agreeing live reports) and one new contradiction | stays, confidence drops; a second contradiction disputes it |

## Consequences
- Nothing is "verified" until a person reports; the map is honest about survey age.
- "Verified beats unverified" in the nearest-alternative ranking only kicks in once people report,
  so the demo's alternative (Kanisa, 200 m from Shule) is chosen by distance.
