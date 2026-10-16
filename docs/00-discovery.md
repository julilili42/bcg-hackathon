# 00 — Discovery: decisions, open questions, defaults

Last updated: 2026-10-16. Change a decision by writing an ADR in `docs/adr/` that supersedes the
old one, then update this table.

## Decided (interactive round, 2026-10-16)

| # | Question | Decision | Consequence |
|---|---|---|---|
| D1 | Time left until pitch | "Does not matter, Claude builds it anyway" | Plan is milestone-based, not date-based. Roles assume Claude Code sessions implement, humans steer, review, and demo. |
| D2 | Platform breadth | Core + one polished use case + one thin use case | Generic entity/report model; water points fully working; clinics loaded from config to prove reuse. |
| D3 | Channels | Phone voice/SMS **and** web map | Keep the Twilio flow from the prototype; add a live MapLibre map and report feed for coordinators. |
| D4 | Stack | Azure Functions (Python 3.12) + Azure SQL | Keep prototype shape. SQLite locally with the same schema. |
| D5 | Azure access | Local for now, deployment documented | Daily work on Azure Functions Core Tools + cloudflared tunnel. `infra/` holds a deploy guide and Bicep skeleton, not executed. |
| D6 | Second use case | Clinics and nutrition centers | Adds a `services` attribute list and `open/closed/no_stock` status vocabulary. Data from Tanzania's Health Facility Registry open dataset. |
| D7 | Seed data | Open WPDx data for one Tanzanian district | Real water point locations and functional status via the WPDx Socrata API (verified: 17,518 Tanzania rows, fields `lat_deg`, `lon_deg`, `status_id`, `status_clean`, `clean_adm1..3`, `served_population`, `staleness_score`). |
| D8 | Development mode | Each teammate drives their own Claude Code session | Four workstreams, contracts first, shared `CLAUDE.md`, directory ownership, small PRs, one integrator. |

## Open questions and the defaults in force

Answer any of these in chat or in a PR to this file. Until then the default applies.

| # | Question | Default in force |
|---|---|---|
| O1 | Team members and strengths | 3–5 people; mapping of people to workstreams in `docs/04-roles-and-workflow.md` is a proposal. |
| O2 | Judging criteria | Live demo and impact story first, technical depth second, code quality third. |
| O3 | Mandatory deliverables | Pitch deck, live demo, public repo. |
| O4 | Everyone uses Claude Code? | Yes. `CLAUDE.md` is the shared contract for sessions. |
| O5 | Primary end user in the demo | Villager with a feature phone reports and asks; coordinator watches the web map. |
| O6 | What "knowledge" means | Structured entity status + crowd reports now. Document Q&A (repair guides, FAQ) is M5 stretch. |
| O7 | Geography and languages | Tanzania, Swahili (`sw-TZ`) and English (`en-US`). **District: Kisarawe, Pwani** (decided at M0: 330 WPDx points, 185 non-functional; Kibaha had only 2 points). |
| O8 | Conflicting reports | Confidence-weighted status with time decay, not last-write-wins (ADR 0006). |
| O9 | Personal data | Caller numbers are personal data. **Pending team confirmation:** has the team reviewed the BCG Guidelines for the Use of AI for Personal Data Processing? Default: store only a salted hash, demo with team phones only (ADR 0004). |
| O10 | Python vs TypeScript | Python for the Functions app, TypeScript for the web map. |
| O11 | Offline / low bandwidth | Phone channel is the offline story. Web map assumes connectivity; tiles cached for the demo venue as a precaution. |
| O12 | Demo freeze | Code freeze two hours before the pitch; only data overlay and slides change after that. |
| O13 | Review strictness | Every PR: green CI + one human review from another workstream. Trivial docs changes may self-merge. |
| O14 | Demo owner and Twilio webhooks | One named person owns the demo machine, the tunnel, and `set_webhooks.sh`. Name goes in `docs/04-roles-and-workflow.md`. |
| O15 | LLM budget | Anthropic key exists. Expect < 2,000 calls during the hackathon at low effort; cost is negligible. Keyword fallback must work without the key. |

## Facts verified on 2026-10-16

- M0 live check: Kisarawe has 330 latest WPDx points (185 `status_id=No`), surveys 2008–2009; Kibaha 2,
  Mkuranga 372, Kisarawe chosen for the stronger non-functional share. The health facility CSV link on
  statistics.go.tz is dead; the openAFRICA `pro-health-facilities.xlsx` (CC-BY, 2016) works and has 16
  Kisarawe facilities with coordinates.
- Azure Functions Core Tools and cloudflared were not on the first dev machine: the app is a FastAPI
  (ASGI) app wrapped for Functions and run with uvicorn locally (ADR 0008).

- WPDx-Basic dataset `eqje-vguj` on `data.waterpointdata.org` answers Socrata SoQL queries without a key
  (count query for Tanzania returned 17,518). Records carry `status_id` (`Yes`/`No`), `status_clean`
  (`Functional`/`Non-Functional`/…), `wpdx_id`, `report_date`, `served_population`, `rehab_priority`,
  `crucialness`, `pressure`, `staleness_score`. Many points have **no human-readable name**; names must
  be generated from `clean_adm3` + source type, with aliases for the demo.
- Azure AI Speech offers Swahili (Tanzania) neural voices `sw-TZ-RehemaNeural` and `sw-TZ-DaudiNeural`,
  a lighter alternative to local MMS-TTS once deployed.
- Tanzania's Ministry of Health publishes the Health Facility Registry (≈11,800 facilities with
  coordinates) as open data on openAFRICA. Good enough for the thin clinics use case via CSV import.
- Claude model for the understanding step: `claude-opus-5-5` (adaptive thinking, effort `low`),
  as in the prototype.
