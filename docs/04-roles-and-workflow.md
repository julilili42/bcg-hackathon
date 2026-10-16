# 04 — Roles and workflow

## Principle

Claude Code sessions write most of the code. Humans decide what to build, keep sessions aligned,
read every diff, and own the demo. One person can hold a process role and drive a workstream at
the same time.

## Process roles (humans)

| Role | Owns | Decides |
|---|---|---|
| **Product & Demo Owner** | Demo script, priorities, the "no" | What is in M1–M4; which task is next when something is red; freeze time |
| **Tech Lead & Integrator** | `main`, contracts (OpenAPI, schemas, domain YAML), Gate 2 | Contract changes; conflict resolution between workstreams; architecture deviations (via ADR) |
| **Data & Trust Steward** | Seed data, status derivation parameters, personal-data and secrets hygiene | Confidence thresholds; what gets logged; dependency approvals |
| **Story & Pitch Lead** | Slides, narrative, impact numbers, video backup | Which features appear on stage and in what order |

Everyone is a **workstream driver** (runs a Claude Code session on one workstream) and a
**reviewer** for another workstream's PRs.

## Proposed mapping (adjust to the real team; names go here)

| Person | Workstream | Process role |
|---|---|---|
| _name_ | WS-A Platform core & data | Tech Lead & Integrator |
| _name_ | WS-B Conversational channel | Product & Demo Owner (owns the Twilio number and tunnel) |
| _name_ | WS-C Web map & dashboard | Story & Pitch Lead |
| _name_ | WS-D Integration, quality & demo | Data & Trust Steward |

Three people: WS-D folds into A and C; the Data & Trust Steward role goes to the WS-A driver.
Five people: WS-B splits into voice flow and brain.

## Rhythm

- **Kick-off (M0):** 30 min together. Agree contracts, mapping above, demo owner, district. Then split.
- **Stand-up:** 10 min every 3–4 hours of work. Each driver: what merged, what is next, what is blocked.
  Red demo steps first.
- **Integration waves:** Tech Lead runs Gate 2 after each wave of merges, at least twice a day.
- **Rehearsal:** end of M2, then three times during M4. Timed, with the backup video updated.

## Git flow

1. `main` is always demoable. Protected: CI green, one review, linear history.
2. Branch per task: `ws-<a|b|c|d>/<topic>`. Short-lived, ideally merged the same day.
3. Small PRs (< 400 lines changed). One concern each. Contract changes are their own PR.
4. Rebase on `main` before opening the PR; squash-merge; delete the branch.
5. Review from another workstream within one stand-up cycle. Reviewer runs the branch when the PR
   touches channels or data.

## Running parallel Claude Code sessions without drift

- Every session starts by reading `CLAUDE.md`, `docs/00-discovery.md`, and its workstream row in
  `docs/01-development-plan.md`. The driver pastes the task from the board into the session.
- Each workstream touches only its directories (ownership table in `CLAUDE.md`). Need something from
  another workstream? Write the interface you need into the contract file via a small PR, or stub it
  behind the interface and leave a `TODO(ws-x)` with the issue number.
- Use `git worktree` (or `EnterWorktree` in Claude Code) when one person runs two sessions.
- Sessions do not install tools or packages from unknown sources, do not change CI, and do not
  touch `main` directly. If a session proposes a destructive git or shell command, the driver stops it.
- Decisions made inside a session that affect others become an ADR or a line in
  `docs/00-discovery.md` in the same PR.
- The driver reads the full diff before opening the PR and marks the lines a reviewer must verify.

## Interface change protocol

1. Open an issue "Contract: <what>" with the proposed change and who it affects.
2. PR touching only the contract file(s) and the ADR or docs line. Tech Lead reviews within the next
   stand-up cycle.
3. Affected workstreams adapt in their next PR. Until then, old and new shapes may coexist behind a
   version field or default.

## Task board

GitHub Issues with labels `ws-a`, `ws-b`, `ws-c`, `ws-d` and `m0`…`m5`, plus `contract` and `demo-red`.
Project board columns: Todo, In session, In review, Done. `demo-red` issues outrank everything.

## Communication

One chat channel for the team, one thread per workstream, one pinned message with: demo owner,
tunnel command, current district, freeze time. Secrets are shared out of band, never in chat history.

## Personal data and secrets (standing rule)

Caller numbers are personal data. We store a salted hash only, demo with team phones only, keep raw
text 30 days, and never log numbers. The team confirms it has reviewed the BCG Guidelines for the Use of
AI for Personal Data Processing before the first real-phone test (tracked as O9 in
`docs/00-discovery.md`). Keys live in `local.settings.json` (git-ignored) on the machines that need
them and nowhere else in the repo.
