# ADR 0002 — Generic domain model configured per use case

**Status:** accepted, 2026-10-16

## Context
The hackathon claim is a *platform*, not a water point app (D2). The second use case, clinics and
nutrition centers (D6), must be demonstrably cheap to add.

## Decision
The core knows `Domain`, `Entity`, `Report`, and `Interaction` only. A domain is a YAML file declaring
entity type, status vocabulary (good/bad sets), attribute schema, matching hints, reply templates per
language, and the alternative-search rule. Channels, brain, map, and nearest-alternative logic read the
domain config and contain no use-case branches.

## Consequences
- Adding a use case = one YAML + one ingest script + optional map icon. This is the demo's platform moment.
- Status values are strings validated against the domain config, not an enum in code.
- Templates live in config, so wording changes need no code review beyond the YAML diff.
- Risk: over-generalizing. Rule: generalize only what the two concrete domains need.
