# ADR 0007 — Parallel Claude Code sessions per workstream, contracts first

**Status:** accepted, 2026-10-16

## Context
Each teammate drives their own Claude Code session (D8). Without shared constraints, sessions re-invent
interfaces, edit the same files, and drift in style.

## Decision
Four workstreams with exclusive directory ownership (table in `CLAUDE.md`). M0 fixes the contracts
(OpenAPI, Pydantic schemas, SQL schema, domain YAML) before feature work. A shared `CLAUDE.md` sets the
session ritual and non-negotiable rules. All changes flow through small PRs with CI and one cross-
workstream human review; the Tech Lead integrates at least twice a day. Contract changes are separate
PRs.

## Consequences
- Early hours go to contracts and scaffolding, which pays back as soon as two sessions run.
- Humans remain accountable: the driver reads every diff before a PR exists.
- Deviations are visible as ADRs or discovery-log lines, not as surprises in `main`.
