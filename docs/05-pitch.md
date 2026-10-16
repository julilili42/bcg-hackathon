# 05 — Pitch: slide by slide

Target: 5 minutes talk + 3 minutes live demo. Numbers below come from the seeded Kisarawe data
(`make seed`, 2026-10-16). Update them if the district or snapshot changes. Slides are built from this
file by the Story & Pitch Lead; speaker notes are in italics.

---

## 1. Title

**Reach** — one number to report, one map to act.
*Fighting World Hunger · team name · hackathon date*

*Hunger is rarely only about food. It is water you cannot reach, a clinic that is closed, a market
that has nothing. All of these have one thing in common: somebody nearby knows, and nobody who could
act does.*

## 2. The problem in one district

- Kisarawe District, Pwani, Tanzania: **330 public water points** in the national dataset.
- **261 of them were not working** at the last survey — 119 broken, 142 dry in the dry season.
- **83,500 of the 107,000 people** those points were built for depend on one that does not work.
- The last survey is from **2008–2009**. Nobody knows what is true today.

*Source: Water Point Data Exchange. The point is not that the data is bad. The point is that the only
way to refresh it is to send a surveyor, and that happens once a decade.*

## 3. The insight

The people who know are already there, and they already have a phone. Not a smartphone: a phone.

- 2G coverage reaches the village long before an app does.
- A 20-second call in Swahili is cheaper than any form.
- What is missing is the place where those calls become shared knowledge and an answer.

## 4. What Reach does (the loop)

1. **Report**: call or text, in Swahili or English. "Kisima cha Shule hakifanyi kazi."
2. **Understand**: Claude reads garbled speech and matches the point; keywords take over if it fails.
3. **Derive**: reports become a status with a confidence score. Old surveys are a weak prior; one
   fresh report overrides them; two people disagreeing shows as *disputed*.
4. **Answer**: the caller hears the nearest working point and the walking time, right away.
5. **Act**: coordinators see the district live and prioritise by people affected.

*Every caller gets something back. That is what makes people call again.*

## 5. Live demo (3 minutes)

Run `docs/06-demo-runbook.md`. Order: map → call → map updates → SMS query → conflict → clinics.

## 6. It is a platform, not a water app

- The second use case, **clinics and nutrition centers**, is one YAML file and one CSV: same phone
  number, same map, same confidence logic. Statuses: open, closed, out of supplies.
- Next candidates with the same shape: food distribution points, market prices, seed and fertilizer
  stock, school feeding.
- Core: entities, reports, derived status. Everything else is configuration or a channel adapter.

## 7. Built for the ground, not the demo

- Works with **no AI key** (keywords), **no Swahili voice model** (Twilio voice), **no network at
  the venue** (snapshot + SQLite).
- Phone numbers are stored only as a salted hash. Twilio requests are signature-checked. Rate limited.
- Open data in, open data out: WPDx and the national health registry seed it; every report is an
  auditable fact, never an overwrite.

## 8. What we would do next week

- Push SMS to people who asked about a point when it flips back to working.
- Repair guides and FAQ per domain, answered over the phone.
- WhatsApp as a third channel; Azure deployment with Azure Speech for Swahili voice.
- A district water engineer's Monday morning view: top 10 repairs by people affected.

## 9. Ask

Introduce us to one district water office or NGO WASH team in Tanzania who would run a two-week pilot
with the number already on the slide.

---

## Impact numbers to have ready

| Number | Value | Source |
|---|---|---|
| Water points in Kisarawe | 330 | WPDx snapshot, `make seed` |
| Not working at last survey | 261 (119 broken, 142 dry) | derived from `status_clean` |
| People served by non-working points | 83,524 of 107,044 | `served_population`, `/api/stats` |
| Wards covered | 15 | `clean_adm3` |
| Health facilities | 16 | Health Facility Registry 2016 |
| Age of the latest survey | 17 years | `report_date` 2008–2009 |
| Reply latency on stage | under 20 ms local, about 2 s with Claude | `/api/interactions` |

## Anticipated questions

- *Why not an app?* Because the people with the information do not have one. Phones first; the map is
  for the few who coordinate.
- *How do you stop false reports?* Confidence from several reports with decay; disputed states are
  visible; one number can report 20 times in 10 minutes at most; everything is auditable.
- *Speech recognition in Swahili?* Twilio does `sw-TZ`; Claude handles the spelling noise; when unsure
  the call asks "did you mean X? press 1".
- *What does it cost?* A Twilio number and minutes; Claude at low effort is cents per thousand calls;
  the rest runs on one small Azure Function and a serverless database.
