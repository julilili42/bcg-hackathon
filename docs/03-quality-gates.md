# 03 — Quality gates

The point of these gates is a demo that does not break and code a stranger can run. Each gate is
cheap enough to run many times a day.

## Gate 0 — Before you commit (local, automatic via `make check` and pre-commit)

- `ruff format --check` and `ruff check` on `api/`
- `mypy --strict api/core` (the rest `mypy` non-strict)
- `pytest api/tests -q` (unit + contract tests, < 60 s)
- `npm run lint && npm run build` in `web/`
- Secret scan (`gitleaks protect --staged`); no file > 5 MB; no `local.settings.json`
- No raw phone number pattern (`\+?\d{9,15}`) in fixtures or tests except the documented fake range

## Gate 1 — Pull request (GitHub Actions, required to merge)

Jobs on every PR to `main`:

| Job | What | Fails when |
|---|---|---|
| `python` | ruff, mypy, pytest with coverage | lint/type error; any test fails; coverage of `api/core` < 80 % |
| `contract` | validate `docs/api/openapi.yaml`; run schema tests against the Functions host with SQLite | response shape drifts from the spec |
| `web` | `tsc --noEmit`, eslint, `vite build` | type or lint error; build fails |
| `smoke` | seed the snapshot, start uvicorn, run `scripts/smoke.sh` (SMS + voice + web API) | any step fails |
| `schema` | `scripts/dump_schema.py` diffed against `schema.sql` | metadata changed without regenerating |
| `secrets` | gitleaks on the diff | any finding |

Branch protection on `main`: all jobs green, one approving review from someone outside the
workstream, linear history, no force pushes.

## Gate 2 — Integration (Tech Lead, after each merge wave, at least twice a day)

- Fresh clone into a temp dir → `make setup` → `make seed` → `make dev` → `make smoke` → `make rehearse`. Must pass.
- Real-phone check by the demo owner when a merge touched `api/channels/`, `api/brain/`, or
  `api/speech/`: one Swahili call, one English SMS.
- Walk the demo script steps 1–4 against `main`. Any red step becomes the top task.

## Gate 3 — Demo readiness (freeze)

State on 2026-10-16: "auto" = verified by `make check`, `make smoke`, `make rehearse` and the
clean-clone run; "human" = needs a person and is tracked in `docs/tasks.md`.

- [x] Clean clone quick start works in < 10 minutes following only the README (auto; a teammate still re-checks: human)
- [ ] Swahili voice report → stored → spoken reply with alternative, **on a real phone** (human; simulated: auto ✓)
- [x] English SMS query → correct reply (auto)
- [x] Map updates within 5 s of a report (auto: API side; visual check on the demo machine: human)
- [x] Conflict demo: two reports → `disputed`, third resolves (auto)
- [x] Clinics domain visible on the map and reachable by SMS (auto)
- [x] Works with `ANTHROPIC_API_KEY` empty (keyword fallback) for the full script (auto, this is how CI runs)
- [x] Works with no TTS models (Twilio voice reads the text) for steps 2–4 (auto)
- [ ] `TWILIO_VALIDATE=1`, `PUBLIC_BASE_URL`, `REPORTER_SALT`, `ADMIN_TOKEN` set on the demo machine (human)
- [x] No secrets in git history (`gitleaks detect`, CI job `secrets`) (auto)
- [ ] Backup video recorded from a full rehearsal (human)
- [x] Demo state restorable: `make seed` or `scripts/demo_reset.sh` (auto)
- [ ] Map tiles for Kisarawe cached in the browser before going on stage: pan and zoom the demo area once on the venue network (human)
- [x] Demo owner card: `docs/06-demo-runbook.md` (name to be filled in: human)

## Definition of done (per task)

1. Behaviour is covered: unit tests for `core/`, a fixture-based smoke test for channel changes, a
   visual check for web changes (screenshot in the PR).
2. `make check` green locally and Gate 1 green in CI.
3. The human author has read the whole diff. Lines where AI-generated logic touches security, data
   handling, or Twilio are called out in the PR.
4. Docs updated when behaviour, a contract, or a decision changed (README, ADR, OpenAPI).
5. Demo impact stated in the PR.

## Test strategy

| Layer | Type | Tool | Owner |
|---|---|---|---|
| `core/status.py`, `core/nearest.py`, `core/matching.py` | unit + property tests | pytest, hypothesis | WS-A |
| Repository layer | integration against SQLite | pytest fixtures | WS-A |
| Ingest | golden-file tests on 50 recorded WPDx rows | pytest | WS-A |
| Brain | contract tests with recorded Claude responses; one live test behind `RUN_LIVE=1` | pytest, respx | WS-B |
| Channels | smoke with recorded Twilio payloads, TwiML assertions | pytest + `scripts/smoke.sh` | WS-B |
| Web | type check, lint, build; Playwright for the three demo views at M3 | tsc, eslint, Playwright | WS-C |
| API contract | OpenAPI validation + schema tests | schemathesis (light) | WS-D |

## Security and data checks (every PR touching them)

- Twilio signature validation path has a test for valid and invalid signatures.
- Reporter hash: test that the raw number never reaches storage or logs.
- Input caps: SMS body ≤ 500 chars, speech result ≤ 500 chars, rate limit 20 messages / 10 min per hash.
- Claude output validated against the JSON schema before use; unknown status values rejected.
- Dependencies pinned (`uv.lock`, `package-lock.json`); new dependency named in the PR.

## Review reminder for all generated code

AI-generated code is a draft. Before merge, read it with the same care as hand-written code: check
logic, hardcoded values, error handling, and input validation. Commit reviewed and tested code only.
