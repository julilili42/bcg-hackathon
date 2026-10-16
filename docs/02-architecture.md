# 02 — Technical architecture

## Context

```
 Villager (feature phone)            Coordinator (browser)
   call / SMS  sw / en                  web map, feed, report form
        │                                       │
        ▼                                       ▼
   ┌─────────┐   webhooks (TwiML)        ┌──────────────┐
   │ Twilio  │ ───────────────────────▶  │  web/ (Vite) │
   └─────────┘ ◀───────────────────────  └──────┬───────┘
        │   speech-to-text sw-TZ / en-US        │ JSON /api/*
        ▼                                       ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ Azure Functions app (Python 3.12)  api/                      │
 │  channels/   twilio_voice  twilio_sms  web_api               │
 │  brain/      understand (Claude Opus 5.5 | keywords)         │
 │  speech/     tts (MMS-TTS local | Azure Speech sw-TZ)        │
 │  core/       domains  schemas  status  nearest  matching     │
 │  storage/    repository (SQLAlchemy Core) migrations         │
 │  ingest/     wpdx  hfr  demo_overlay                         │
 └───────────────────────────┬──────────────────────────────────┘
                             ▼
                SQLite (local)  |  Azure SQL (deployed)
```

External: Twilio (voice, SMS), Anthropic API (understanding), WPDx Socrata API and Tanzania HFR
CSV (seed data), OpenStreetMap raster tiles (map). All optional at runtime except the database.

The Functions app is a FastAPI (ASGI) application wrapped by `azure.functions.AsgiFunctionApp`; locally
it runs under uvicorn with no Functions runtime (ADR 0008).

## Design principles

1. **Channel-agnostic core.** Everything reaches the core as an `InboundMessage` and leaves as an
   `OutboundReply`. Voice, SMS, and web are adapters.
2. **Use cases are configuration.** A domain is a YAML file: entity type, status vocabulary,
   attributes, matching hints, reply templates per language, alternative-search rules. Adding
   clinics must not require code in `core/`.
3. **Reports are facts, status is derived.** We never overwrite status; we append reports and
   compute status + confidence from them. This makes conflict, decay, and audit possible.
4. **Degrade gracefully.** No Anthropic key → keywords. No TTS models → Twilio's English voice.
   No network → SQLite copy of the demo state.
5. **Local first, cloud ready.** Same code and schema run on a laptop and in Azure.

## Domain model

```
Domain          id (water|health), entity_type, statuses[], attributes schema,
                matching hints, reply templates {sw,en}, alternative rule

Entity          id, domain_id, name, aliases[], lat, lon, adm1, adm2, adm3,
                attributes (JSON), source (wpdx|hfr|report|demo), external_id,
                current_status, confidence, last_report_at, served_population

Report          id, entity_id, reporter_hash, channel (voice|sms|web|import),
                lang, raw_text, status_claimed, note, weight, created_at

Interaction     id, channel, sender_hash, lang, body, reply, intent,
                entity_id?, latency_ms, created_at      -- for feed and debugging
```

### Status derivation (`core/status.py`, pure functions, unit-tested)

For an entity, take live reports from the last 90 days plus all imported baselines. Each report has
weight `w = base × decay(age)` with `decay = 0.5 ** (age_days / half_life)`; `base` is the weight stored
on the report (live voice/SMS 1.0, web 1.2, WPDx/HFR imports 0.4, demo overlay 0.25), half-life 7 days
for live reports, 365 days for imports with a floor of 0.15. Sum weights per claimed status. The leader
wins; `confidence = leader / total × min(1, total / 1.5)`. Among live reports only: runner-up ≥ 75 %
of the leader and live total ≥ 1.5 → `disputed`; total ≤ 0.05 → `unknown`; confidence < 0.3 → shown as "unverified".
Worked examples in ADR 0009.

### Nearest working alternative (`core/nearest.py`)

Same domain, status `ok` (or the domain's "good" statuses), confidence ≥ 0.5, within 15 km by
bounding box, sorted by haversine distance; walking minutes = km / 5 × 60 × 1.3 path factor. Returns
up to three candidates; the reply uses the first, the map shows all.

### Entity matching (`core/matching.py` + brain)

Candidates are narrowed by the domain and, if mentioned, by village or ward. Claude receives up to
200 candidate names with aliases and returns the best match plus a confidence. Below 0.6 the voice
flow asks for confirmation; SMS replies with the top two choices. Keyword fallback uses normalized
token overlap on names and aliases.

## Channel flows

**Voice.** `/api/voice` → TwiML `<Gather input="speech" language="sw-TZ">` with greeting and "press 2
for English" → `/api/voice/handle` with `SpeechResult` → brain → report stored → reply text →
TTS wav (cached) → `<Play>` → hang up. Confirmation branch when match confidence is low.

**SMS.** `/api/sms` → brain detects language and intent → report or query → text reply via TwiML
`<Message>`.

**Follow-ups (ADR 0010).** When a status arrives without a place, two places tie, or one place is
uncertain, the service stores one open question per sender (`conversations`, 10 min) and asks it. The
next message answers it (yes/no, 1/2, or a name) or replaces it. Voice gathers the answer on
`/api/voice/answer`; SMS simply continues the thread. At most two questions, then a help text.

**Web.** `GET /api/entities?domain=water&bbox=...` (GeoJSON), `GET /api/reports?domain=&since=`,
`GET /api/entities/{id}`, `POST /api/reports` (web form), `GET /api/stats?domain=`. Static
`web/dist` served at `/` by the Functions app for the demo; `vite dev` with proxy during development.

**Virtual demo phone.** The web map embeds a photographed 3310 (`web/public/phone.webp`, hit areas and
LCD position from `web/src/phone-layout.json`, generated by `scripts/prep_phone_photo.py`; drawn SVG
fallback) in `web/src/phone.ts` that drives the same conversation through `/api/sim/voice*` and `/api/sim/sms` (`channels/sim.py`): unsigned twins of
the Twilio webhooks sharing the handler implementations, enabled by `DEMO_PHONE` (default on, off in
production). The browser parses the returned TwiML (`web/src/twiml.ts`), shows `<Say>` text, plays
`<Play>` audio, and posts the typed, spoken (Web Speech API), or keyed answer to the `<Gather>` action.

## Brain (understanding step)

Model `claude-opus-5-5`, Python SDK. Omit `thinking` (adaptive), `output_config={"effort": "low",
"format": <JSON schema>}`, `fallbacks="default"` with beta `server-side-fallback-2026-07-01`, request
timeout 4 s. Output schema:

```json
{"intent": "report|query|help|other",
 "entity": {"name": "...", "confidence": 0.0},
 "status": "ok|broken|empty|open|closed|no_stock|null",
 "lang": "sw|en",
 "place_hint": "..." }
```

The prompt is domain-specific text from the YAML plus the candidate list. Candidate list first,
user text last, so the stable part of the prompt can be cached.

## Data model (SQL, one schema for SQLite and Azure SQL)

```sql
domains      (id TEXT PK, config_json TEXT, updated_at)
entities     (id TEXT PK, domain_id FK, name, lat REAL, lon REAL, adm1, adm2, adm3,
              attributes_json, source, external_id, current_status, confidence REAL,
              last_report_at, served_population INT)
aliases      (entity_id FK, alias TEXT, PRIMARY KEY (entity_id, alias))
reports      (id INTEGER PK, entity_id FK, reporter_hash, channel, lang, raw_text,
              status_claimed, note, weight REAL, created_at)
interactions (id INTEGER PK, channel, sender_hash, lang, body, reply, intent,
              entity_id, latency_ms, created_at)
conversations(key TEXT PK "<channel>:<reporter_hash>", channel, domain_id, lang, kind,
              status_claimed, candidates_json, raw_text, attempts, created_at, expires_at)
```

Indexes on `entities(domain_id, lat, lon)`, `reports(entity_id, created_at)`. `api/reach/storage/db.py`
(SQLAlchemy metadata) is the source of truth; `make schema` regenerates `schema.sql` and CI diffs it.

## Domain configuration example

```yaml
# api/core/domains/health.yaml
id: health
entity_type: clinic
statuses:
  good: [open]
  bad: [closed, no_stock]
attributes:
  services: list[string]       # e.g. [nutrition, maternal, outpatient]
  level: string                # dispensary | health_centre | hospital
matching_hints: ["zahanati", "kituo cha afya", "hospitali", "clinic", "dispensary"]
alternative:
  radius_km: 25
  require_attribute: null
templates:
  sw:
    recorded: "Asante. Tumeandika kwamba {name} {status_sw}."
    nearest: "Kituo cha karibu kinachofanya kazi ni {alt_name}, dakika {minutes} kwa miguu."
  en:
    recorded: "Thank you. We recorded that {name} is {status_en}."
    nearest: "The nearest open facility is {alt_name}, about {minutes} minutes on foot."
```

## Seed data

- **WPDx** (`ingest/wpdx.py`): Socrata SoQL against `eqje-vguj`, `$where=clean_country_name='Tanzania'
  AND clean_adm2='<district>' AND is_latest=true`, paged by `$limit/$offset`. Map `status_id`
  Yes→`ok`, No→`broken`, else `unknown`; keep `status_clean`, `water_tech_clean`, `served_population`,
  `report_date` as the baseline report's timestamp (low weight by age). Name =
  `f"{clean_adm3} {water_source_clean} {n}"`. `wpdx_id` → `external_id`.
- **HFR** (`ingest/hfr.py`): CSV from the Ministry of Health open dataset filtered to the district;
  name, facility type, coordinates, services where present; status `open` baseline.
- **Demo overlay** (`ingest/demo_overlay.py`, `data/demo/aliases.csv`): memorable names such as
  "Shule", "Kanisa", "Soko" on real points in Kisarawe ward (the generated name stays as an alias),
  plus a weak baseline status so the demo starts from a known state. Clinics keep their registry
  names; "Zahanati Msanga" is an alias generated by the health import.

## Repository layout (target)

```
api/            Azure Functions app
  function_app.py  channels/  brain/  speech/  core/  storage/  ingest/  tests/
web/            Vite + TypeScript + MapLibre
data/           small seed snapshots, demo overlay (no large binaries)
infra/          Azure deploy guide, Bicep skeleton (not executed in the hackathon)
scripts/        set_webhooks.sh, smoke.sh, seed.sh
docs/           this plan, ADRs, openapi.yaml
```

## Local development topology

`make dev` → uvicorn on :7071 with SQLite `data/local.db` (`func start` in `api/` also works); `make web` → Vite on
:5173 proxying `/api`; `make smoke` → replays fixtures in `api/tests/fixtures/twilio/`;
`cloudflared tunnel --url http://localhost:7071` + `scripts/set_webhooks.sh <url>` for a real phone.
Only the demo owner points the shared number anywhere.

## Azure deployment (documented, optional)

Function App (Linux, Python 3.12, Premium plan for cold starts), Azure SQL serverless, Static Web App
or the Functions static route for `web/dist`, Azure AI Speech for `sw-TZ` TTS instead of torch. Secrets
in App Settings or Key Vault. `infra/README.md` holds the steps; `infra/main.bicep` the skeleton.
