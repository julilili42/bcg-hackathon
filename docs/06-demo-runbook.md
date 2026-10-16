# 06 — Demo runbook and rehearsal protocol

One card for the demo owner. Print it.

## Before the demo (T-60 min)

```bash
make seed                                  # fresh Kisarawe state with demo aliases
make build-web && make dev                 # API + map on http://localhost:7071
cloudflared tunnel --url http://localhost:7071           # second terminal; copy the https URL
scripts/set_webhooks.sh https://<tunnel-host>            # Twilio number now rings here
# api/local.settings.json: PUBLIC_BASE_URL=https://<tunnel-host>, TWILIO_VALIDATE=1,
#                          REPORTER_SALT=<random>, ADMIN_TOKEN=<random>, ANTHROPIC_API_KEY=<key>
make rehearse                              # all 8 steps PASS, then: scripts/demo_reset.sh
```

Open the map in a browser at full width (`http://localhost:7071/?phone=open` shows the demo phone open),
water tab, zoom on Kisarawe ward (Shule and Kanisa visible).
Phone 1 and phone 2 on the table, both saved with the Reach number. Virtual phone visible (Settings → Show
demo phone). Backup video open in another tab.

## On stage (3 minutes)

| # | Say | Do | Expect |
|---|---|---|---|
| 1 | "This is Kisarawe. 330 water points, 261 not working at the last survey, 17 years ago." | Point at the stats tiles | Map with mostly red/amber faded points |
| 2 | "Now a villager calls." | Phone 1: call, after the greeting say **"Kisima cha Shule hakifanyi kazi"** | Spoken reply: Shule recorded broken, nearest working Kanisa, 4 minutes on foot |
| 3 | "Watch the map." | Nothing | Within 5 s: Shule turns red and pulses; feed shows the report; click it: confidence ~0.65, verified |
| 4 | "English works too, and so does SMS." | Phone 2: SMS **"Is Shule working?"** | Reply: Shule is broken, nearest alternative with walking time |
| 5 | "What if people disagree?" | Phone 2: SMS **"Shule inafanya kazi"**; then phone 1: SMS **"Shule imeharibika"** | Map: Shule amber *disputed*; after the third report back to red |
| 6 | "Same number, different use case." | Click **Clinics**; phone 1: SMS **"Zahanati Msanga imefungwa"** | Msanga Dispensary closed, alternative Marui Dispensary; show `health.yaml` |
| 7 | "On Monday morning a district engineer opens this." | Sort by people affected in the detail panel; close | Applause, ideally |

If the real phone fails: use the virtual phone at the bottom right of the map (hover, green Call button or
the middle key, type or speak the same sentences; English switch for step 4; Phone 2 for the dispute;
red Hang up to end). If the network fails: the map, API and virtual
phone are all local; only the real phone needs the tunnel. If everything fails: video.

## Rehearsal protocol (three times before the pitch)

1. `scripts/demo_reset.sh` (or `make seed`), then run the stage table with real phones. Time it.
2. Record the second rehearsal as the backup video (screen + phone audio).
3. After each rehearsal, write down: what was slow, what was misheard, what the audience would ask.
   Fix wording in `api/reach/core/domains/*.yaml`, not code, where possible.
4. Freeze two hours before the pitch: only `data/demo/aliases.csv` and slides may change.

## Automated rehearsal

`make rehearse` runs the same seven steps against the API with Twilio's magic test numbers and prints
PASS/FAIL with timings. CI runs the smoke subset; the full rehearsal is for the demo machine.
