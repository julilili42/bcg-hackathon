# ADR 0003 — Seed from WPDx and Tanzania HFR open data

**Status:** accepted, 2026-10-16

## Context
The team chose real open data over fictional seed (D7). Verified on 2026-10-16: the WPDx-Basic Socrata
dataset `eqje-vguj` returns 17,518 Tanzanian water points with coordinates, `status_id`/`status_clean`,
admin levels, served population, and staleness fields, without an API key. Tanzania's Health Facility
Registry is published as open data with coordinates.

## Decision
Seed water points for one district from WPDx (`is_latest=true`), imported as low-weight baseline
reports dated by `report_date`. Seed clinics from the HFR CSV filtered to the same district. Human
names are generated from ward + source type because WPDx points carry none; a demo overlay gives a
handful of real points near the demo location memorable Swahili names (the generated name is kept as
an alias). No fictional entities, no fictional coordinates.

## Consequences
- Credible map and real impact numbers (served population behind non-functional points).
- Stale WPDx status appears as "unverified" until a fresh report; this is a feature of the story.
- Name generation and aliases are needed for speech matching; owned by WS-A, overlay by WS-D.
- District chosen at M0 by WPDx row count; Kibaha (Pwani) preferred for continuity if coverage is good.
