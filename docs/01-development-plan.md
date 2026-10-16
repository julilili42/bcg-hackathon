# 01 — Development plan

## Vision

Hunger is rarely only about food. When the village water point breaks, people walk hours for water,
children miss school, and the clinic runs out of supplies nobody reported. **Reach** gives communities
one place where status becomes shared knowledge, through the channel people already have: a phone.

- A villager calls or texts, in Swahili or English: "Kisima cha Shule hakifanyi kazi."
- Reach records the report, updates the point's status with a confidence score, and answers right away:
  the nearest working point and the walking time.
- Coordinators see the district live on a map, with disputed and stale points highlighted and a feed of
  what people are saying.
- The same platform, configured rather than rebuilt, does the same for clinics and nutrition centers.

Pitch line: *"One number to report, one map to act, one platform for every point that keeps a
community fed."*

## Scope

**In scope (M1–M4)**

- Generic knowledge core: domains, entities, reports, status derivation with confidence, nearest
  working alternative.
- Water domain polished: WPDx seed for one district, voice + SMS in sw/en, web map, report feed.
- Clinics domain thin: config + CSV import + visible on the map and reachable by SMS.
- Quality: CI, smoke tests with recorded Twilio payloads, demo-readiness checklist, backup video.
- Documentation: README quick start verified by a non-author, deployment guide for Azure.

**Out of scope (unless M5 stretch)**

- Document Q&A over repair guides and FAQ. WhatsApp channel. Push alerts to subscribers.
- Authentication and roles in the web UI. Multi-country, additional languages.
- Executed Azure deployment (documented only, per D5).

## Milestones

Milestones are ordered, not dated. Each has exit criteria that WS-D verifies on `main`.
State on 2026-10-16: M0–M3 implemented and green (`make check`, `make smoke`, `make rehearse`, clean-clone
run). M4: pitch content (`docs/05-pitch.md`), runbook (`docs/06-demo-runbook.md`) and three automated
rehearsals (`docs/rehearsals.md`) are done; real-phone rehearsals, the backup video, and building the
slides need people and are on `docs/tasks.md`.

### M0 — Foundations (before parallel work starts)

Owner: Tech Lead with WS-D. Everything else waits for this.

- Repo skeleton: `api/`, `web/`, `data/`, `infra/`, `scripts/`, `Makefile`, `.github/workflows/ci.yml`.
- Contracts committed: `docs/api/openapi.yaml`, `api/core/schemas.py`, `api/storage/schema.sql`,
  `api/core/domains/water.yaml` and `health.yaml` (fields may still be empty but shapes are fixed).
- Dev loop works from a clean clone: `uv sync`, `make dev` starts the Functions host with SQLite,
  `make check` runs green on an empty project, `make smoke` replays one recorded SMS fixture.
- District chosen by a WPDx count query; written in `docs/00-discovery.md` O7.
- Task board created (GitHub Issues with labels `ws-a..d`, `m1..m5`).

Exit: a teammate who did not set it up clones, runs `make dev` and `make smoke`, both pass.

### M1 — Walking skeleton (thin end-to-end)

- WS-A: WPDx ingest for the district into `entities`; generated names + alias table; nearest query.
- WS-B: SMS in → brain (Claude or keywords) → report stored → reply with nearest working point.
- WS-C: map shows seeded points colored by status, polling `/api/entities` every 5 s.
- WS-D: CI running lint, types, unit tests, smoke; PR template enforced.

Exit: send one SMS "Shule imeharibika" through the smoke fixture, the point turns red on the map,
the reply names an alternative. Demonstrable end to end without a real phone.

### M2 — Depth

- WS-A: status derivation with confidence and decay (ADR 0006); `disputed` and `unknown` states;
  report feed endpoint; health domain loaded from config + HFR CSV.
- WS-B: voice flow sw/en with Twilio Gather, TTS replies (MMS-TTS locally), follow-up questions only
  when a slot is missing (ADR 0010): which point, did you mean X, A or B; language detection for SMS.
- WS-C: report feed panel, entity detail with confidence and last-verified, domain switcher
  (water / clinics), web report form for field officers.
- WS-D: recorded voice fixtures, demo data overlay (friendly aliases for the demo points), first
  rehearsal of the demo script.

Exit: full demo script runs on a real phone with the team's numbers; both domains visible.

### M3 — Hardening

- Fallbacks: no Anthropic key → keywords; Claude timeout 4 s; Twilio STT returns nothing → re-prompt once.
- Security: Twilio signature validation on, rate limit per reporter hash, input length caps.
- Performance: SMS reply < 3 s end to end, voice reply < 6 s including TTS; TTS cache warmed for
  templates.
- Data: WPDx baseline reports marked low-confidence by age; stale points shown as "unverified".
- README quick start verified by someone who did not write it.

Exit: demo-readiness checklist in `docs/03-quality-gates.md` fully green.

### M4 — Demo and pitch

- Three full rehearsals, each timed; backup video recorded from a rehearsal.
- Slides: problem, the call, the map, the platform claim (clinics in 1 config file), impact numbers
  from WPDx (served population behind non-functional points in the district), what is next.
- Freeze two hours before the pitch.

### M5 — Stretch (only after M4 is green)

- Knowledge documents: repair guides and FAQ per domain, Q&A over them from the phone.
- Push alerts: SMS to subscribers of a point when its status flips.
- WhatsApp via Twilio as a third channel. Azure deployment executed with Azure Speech TTS.

## Workstreams and deliverables

| WS | Name | Core deliverables | Depends on |
|---|---|---|---|
| A | Platform core & data | Domain configs, entity/report models, migrations, repository layer, status derivation, nearest alternative, WPDx + HFR ingest, seed script | M0 contracts |
| B | Conversational channel | Twilio voice + SMS adapters, TwiML rendering, brain (Claude structured output + keyword fallback), TTS with cache, sw/en reply templates, `smoke.sh`, `set_webhooks.sh` | A: `core.schemas`, repository interface |
| C | Web map & dashboard | Vite + TS + MapLibre app, entity layer with status colors and confidence, report feed, entity detail, domain switcher, web report form, read-only API endpoints | A: OpenAPI, entity endpoints |
| D | Integration, quality & demo | Makefile, CI, fixtures, demo overlay, rehearsal protocol, backup video, README verification, Azure deploy guide, pitch alignment | all |

With three people, WS-D folds into the Tech Lead (A) and the web owner (C). With five, split B into
voice and brain.

## Demo script (what must work on stage)

1. **Map** of Kisarawe district with 330 real WPDx points: green working, red broken, grey unverified,
   amber disputed. Sidebar: "X points, Y non-functional, Z people affected."
2. **Call** the number. Swahili greeting. Judge or teammate says: "Kisima cha Shule hakifanyi kazi."
   Reach records it and answers: "Asante. Shule imeandikwa kama imeharibika. Kisima cha karibu
   kilichoripotiwa kufanya kazi ni Kanisa, dakika 4 kwa miguu." (Shule and Kanisa are aliases on two
   real points 200 m apart in Kisarawe ward.)
3. **Map updates live** within 5 s: the point turns red and pulses, the report appears in the feed,
   the detail panel shows confidence about 0.65 and "verified".
4. **SMS** in English: "Is Shule working?". Reply in English: broken, plus the nearest alternative and
   walking time.
5. **Conflict**: a second phone reports the same point as working. Map shows amber "disputed", feed
   shows both reports. A third report resolves it. One sentence on why this matters for trust.
6. **Platform claim**: switch to the clinics tab. Same map, same phone number, "Zahanati Msanga
   imefungwa" marks Msanga Dispensary closed and names Marui Dispensary as the alternative. Show
   `health.yaml`: the whole second use case is one config file and one CSV.
7. **Close**: what a district water engineer does with this on Monday morning.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| WPDx points have no names; speech recognition will not match `wpdx_id` | Generate names from ward + source type; alias table; demo points get memorable aliases; Claude matches loosely and the voice flow confirms uncertain matches. |
| Torch + MMS-TTS is heavy (~300 MB models, slow cold start) | Pre-render all template replies at startup into `audio/`; only entity names are synthesized live. Azure Speech `sw-TZ` voices documented as the deployed alternative. |
| Twilio STT accuracy on Swahili place names | Few, distinct demo names; confirmation prompt; SMS as the fallback channel in the script. |
| One Twilio number, one tunnel | Demo owner rule; everyone else develops against `make smoke` fixtures, never the real number. |
| Parallel Claude sessions drift apart | Contracts first (M0), directory ownership, small PRs, Tech Lead integrates twice a day. |
| Claude API latency or outage on stage | Timeout 4 s → keyword fallback; the demo script works on keywords alone. |
| WPDx status is years old | Imported status enters as a low-confidence baseline; map shows "unverified" until a fresh report. |
| Personal data in events | Hash-only reporter identity; fixtures with fake numbers; retention of raw text 30 days. Confirmation of the BCG personal-data guideline review is still open (O9). |
| Demo venue network | Tiles cached, backup video, SQLite copy of the demo state. |
