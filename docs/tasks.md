# Task board

Local board (GitHub Issues can mirror it once the team agrees). Columns: Todo, In session, In review, Done.
Labels in brackets: workstream, milestone, `demo-red` outranks everything.

## Done

- [x] M0 repo skeleton, contracts (OpenAPI, schemas, SQL metadata, domain YAML), Makefile, CI [ws-d, m0]
- [x] M0 district chosen: Kisarawe, Pwani (330 WPDx points, 56 % non-functional) [ws-a, m0]
- [x] M1 WPDx snapshot + ingest, generated names, demo alias overlay [ws-a, m1]
- [x] M1 SMS flow → keyword/Claude understanding → report → reply with alternative [ws-b, m1]
- [x] M1 map with status colors, polling, stats [ws-c, m1]
- [x] M1 CI: ruff, mypy, pytest + coverage, smoke, web build, gitleaks [ws-d, m1]
- [x] M2 status derivation with confidence, decay, disputed/unknown (ADR 0006, 0009) [ws-a, m2]
- [x] M2 health domain from config + HFR CSV (16 Kisarawe facilities) [ws-a, m2]
- [x] M2 voice flow sw/en, confirmation step, retry, TTS provider interface [ws-b, m2]
- [x] M2 feed, entity detail, domain switcher, web report form, conversations panel [ws-c, m2]
- [x] M3 fallbacks (no key → keywords, 4 s timeout), Twilio signature validation, rate limit, input caps [ws-b, m3]
- [x] Follow-up questions on SMS and voice when a slot is missing (ADR 0010) [ws-b]
- [x] Virtual Nokia-style demo phone on the map with `/api/sim/*` endpoints and DEMO_PHONE flag [ws-c, ws-b]
- [x] M3 clean-clone verification: `make setup`, `make seed`, `make check`, smoke, rehearsal (automated) [ws-d, m3]
- [x] M4 automated rehearsals ×3 logged in `docs/rehearsals.md`; pitch in `docs/05-pitch.md`; runbook in `docs/06-demo-runbook.md` [ws-d, m4]

## Todo

- [x] Virtual phone uses the real 3310 photo (cut out, straightened, clickable keys), checked by headless screenshot (`docs/img/demo-phone.png`) [ws-c]
- [ ] M2 real-phone test of the voice flow with the shared Twilio number (demo owner) [ws-b, m2, human]
- [ ] M2 MMS-TTS models downloaded on the demo machine (`uv sync --extra tts`, `scripts/download_models.py`) [ws-b, m2, human]
- [ ] M3 README quick start verified by a teammate who did not write it [ws-d, m3, human]
- [ ] M4 three timed rehearsals on a real phone; backup video [all, m4, human]
- [ ] M4 slides from `docs/05-pitch.md` [story lead, m4, human]
- [ ] O9 confirm the BCG personal-data guideline review before the first real-phone test [steward, m2, human]
- [ ] Set `REPORTER_SALT` and `ADMIN_TOKEN` in `api/local.settings.json` on the demo machine [steward, m3, human]

## Stretch (M5)

- [ ] Document Q&A over repair guides and FAQ per domain
- [ ] Push SMS to subscribers when a point flips to broken
- [ ] WhatsApp channel via Twilio
- [ ] Azure deployment executed (`infra/README.md`)
