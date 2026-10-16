# CLAUDE.md — rules for Claude Code sessions in this repo

Reach is a knowledge platform for community infrastructure status (water points first, clinics second),
reachable by phone call, SMS, and a web map. Read `docs/01-development-plan.md` and the section of
`docs/04-roles-and-workflow.md` for your workstream before changing anything.

## Session ritual

1. Start: read this file, `docs/00-discovery.md` (decisions), and your workstream's deliverables in
   `docs/01-development-plan.md`. Check `git log --oneline -15` and open PRs (`gh pr list`).
2. Work on a branch named `ws-<letter>/<short-topic>` (for example `ws-b/voice-flow`). Never commit
   directly to `main`.
3. Before opening a PR: run `make check` (lint, types, tests, web build). Fill in the PR template.
   The human driving this session reads the whole diff before the PR is opened.
4. End: leave the branch pushed, the PR open or merged, and the task status updated.

## Non-negotiable rules

- **No secrets in the repo.** Never write API keys, tokens, or connection strings into any tracked
  file. `local.settings.json` is git-ignored; only `local.settings.json.example` with empty values is
  committed. If a task seems to need a secret in a file, stop and say so.
- **No raw phone numbers.** Reporter identity is a salted SHA-256 hash (`REPORTER_SALT` setting).
  Logs, fixtures, and tests use fake numbers only. See `docs/adr/0004-reporter-hash.md`.
- **Stay in your workstream's directories** (ownership table below). To change a shared contract
  (`docs/api/openapi.yaml`, `api/reach/core/schemas.py`, `api/reach/storage/db.py`, `api/reach/core/domains/*.yaml`),
  open a small contract-only PR first and tag the Tech Lead.
- **Tests for `api/reach/core/`** are mandatory: status derivation and nearest-alternative logic are pure
  functions and must have unit tests. Channel code is covered by smoke tests with recorded fixtures.
- **Never run** `git push --force`, `git reset --hard`, `git clean`, `rm -rf` outside your scratch
  files, or destructive SQL without an explicit human instruction in the current session.
- **Dependencies:** add Python packages via `uv add`, web packages via `npm install --save-exact`.
  No packages from git URLs or unknown registries. Say when you add a dependency and why.
- **AI-generated code is a draft.** Say so in the PR when a change touches security, data handling,
  or the Twilio flow, and point the reviewer at the exact lines to verify.

## Tech conventions

- Python 3.12, `uv`, FastAPI app (`api/reach/app.py`) wrapped by Azure Functions in
  `api/function_app.py` (ADR 0008). Locally: `make dev` runs uvicorn on :7071; no Functions Core Tools
  needed. `ruff` (format + lint), `mypy --strict` over the whole `reach` package, `pytest` with coverage
  ≥ 80 %. SQLite locally, Azure SQL when deployed, one schema via SQLAlchemy Core (`storage/db.py` is
  the source of truth; `make schema` regenerates `schema.sql`).
- Web: TypeScript strict, Vite, MapLibre GL JS, no framework unless the team agrees. `eslint` + `tsc`.
- Claude API (Python SDK `anthropic>=1.15`): model `claude-opus-5-5`, omit the `thinking` parameter
  (adaptive by default), `output_config={"effort": "low"}` for the understanding step so replies stay
  under ~2 s, structured outputs via `output_config.format`, `fallbacks="default"` with beta
  `server-side-fallback-2026-07-01`. Timeout 4 s, then keyword fallback. Never append date suffixes to
  model IDs.
- Twilio: signature validation on by default (`TWILIO_VALIDATE=1`), off only for local smoke tests.
- Logging: one JSON line per inbound message with `channel`, `lang`, `intent`, `entity_id`,
  `latency_ms`, `src`. Never log the raw sender number.
- Smoke and rehearsal against a real server: `scripts/with_server.py -- scripts/smoke.sh` starts and
  stops its own uvicorn; `make rehearse` runs the demo script against `make dev`.
- Commits: imperative mood, one topic per commit, reference the task (`WS-B: voice flow, sw-TZ gather`).

## Workstream ownership

| Workstream | Owns | Must not touch without a contract PR |
|---|---|---|
| WS-A Platform core & data | `api/reach/core/`, `api/reach/storage/`, `api/reach/ingest/`, `data/` | `api/reach/channels/`, `web/` |
| WS-B Conversational channel | `api/reach/channels/twilio*.py`, `twiml.py`, `api/reach/brain/`, `api/reach/speech/`, `scripts/set_webhooks.sh`, `scripts/smoke.sh` | `api/reach/core/`, `web/` |
| WS-C Web map & dashboard | `web/`, `api/reach/channels/web_api.py`, `docs/api/openapi.yaml` (proposals) | `api/reach/core/`, `api/reach/brain/` |
| WS-D Integration, quality & demo | `.github/`, `Makefile`, `infra/`, `docs/`, `README.md`, demo data overlay in `data/demo/` | feature code in any workstream |

Shared and owned by the Tech Lead: `api/function_app.py`, `api/reach/app.py`, `pyproject.toml`,
`docs/api/openapi.yaml`, `api/reach/core/schemas.py`, `api/reach/storage/db.py`,
`api/reach/core/domains/*.yaml`.

## Where to look

- Decisions and why: `docs/adr/`. If you disagree with one, write a new ADR that supersedes it;
  do not silently diverge.
- Quality bar and definition of done: `docs/03-quality-gates.md`.
- Demo script (what must work on stage): `docs/01-development-plan.md` → "Demo script".
