# Reach Gateway

Phone-in water point status line. A caller says the name of a water point and whether it works,
in **Swahili** or **English**. The system records it and answers right away with the nearest
working water point. Also works over SMS.

## Quick start for the team

Everything runs on one Twilio account and one phone number (**+1 865 459 8142**).
Only one machine can receive the calls at a time: whoever runs the tunnel runs the demo.

```bash
git clone <repo> && cd reach-gateway
uv sync                                   # Python 3.12 venv + deps
uv run download_models.py                 # the two TTS models, ~300 MB, once
cp local.settings.json.example local.settings.json
#   -> fill in TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and ANTHROPIC_API_KEY (ask Julian, never commit them)
uv run func start                         # local host on :7071, needs Azure Functions Core Tools
cloudflared tunnel --url http://localhost:7071    # second terminal, prints a public https URL
./set_webhooks.sh https://<that-url>      # third terminal: Twilio now sends calls/SMS to YOUR machine
```

Then call or text +1 865 459 8142. Dashboard: http://localhost:7071/api/dashboard

Tools you need once: `uv` (brew install uv), `cloudflared` (brew install cloudflared),
Azure Functions Core Tools (`npm i -g azure-functions-core-tools@4`).
No Twilio SDK, no Azure account: Twilio is driven by plain webhooks + `set_webhooks.sh`.

```
Call/SMS ──▶ Twilio ──▶ /api/voice  (greeting, speech-to-text sw-TZ / en-US)
                        /api/voice/handle ──▶ brain.py ──▶ SQL (waterpoints, events)
                        ◀── audio reply (local MMS-TTS) or text ◀──┘
Dashboard: /api/dashboard
```

| File | Does |
|---|---|
| `function_app.py` | Twilio webhooks, TwiML, routes |
| `brain.py` | understand (Claude or keywords) → update status → reply text, sw/en templates |
| `tts.py` | text → wav with Meta MMS-TTS, cached in `audio/` |
| `db.py` | `events` + `waterpoints`, Azure SQL or SQLite |
| `download_models.py` | fetches the two TTS models into `models/` |
| `waterpoints.csv` | seed data (fictional names around Kibaha, TZ) |
| `smoke.sh` | simulates Twilio against the local host |
| `set_webhooks.sh` | points the Twilio number at your tunnel or Azure URL |

## Run locally

```bash
uv sync                          # Python 3.12 venv + deps
uv run download_models.py        # ~300 MB, once. Without it: Twilio's own voice (English only)
uv run brain.py && uv run tts.py # self-checks
cp local.settings.json.example local.settings.json   # fill in Twilio values
func start                       # http://localhost:7071  (uses .venv)
./smoke.sh                       # second terminal
```

Public URL for a real phone: `cloudflared tunnel --url http://localhost:7071`, then
`./set_webhooks.sh https://<tunnel-host>`. Only one machine can own the webhooks at a time;
whoever runs the tunnel runs the demo.

## Settings (`local.settings.json` / Azure App Settings)

| Key | |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | from console.twilio.com |
| `TWILIO_VALIDATE` | `1` in Azure: only signed Twilio requests. `0` locally for smoke.sh |
| `ANTHROPIC_API_KEY` | optional; `brain.py` then uses Claude Opus 5.5 (effort low, ~2 s). Without it: keyword matching |
| `SQL_CONN` | optional; without it SQLite `events.db` |

## Call flow

1. Greeting in Swahili: say the water point and its state. Press 2 for English.
2. Twilio transcribes (`sw-TZ` or `en-US`). `brain.reply()` asks Claude for `{point, status, lang}`
   (loose name matching survives speech-recognition errors), sets `ok|broken|empty` if the caller
   reported, and answers with the nearest working point and walking minutes. SMS answers in the
   language the message was written in.
3. Reply spoken with MMS-TTS (`facebook/mms-tts-swh` / `-eng`), then hang up.

Why speech-to-text is Twilio's and not a local model: Twilio Gather supports `sw-TZ` out of the box and
Whisper-small is weak on Swahili. Text-to-speech is local because Twilio has no Swahili voice.

## Deploy to Azure

Function App (Linux, Python 3.12) + Azure SQL with `schema.sql`. `uv export > requirements.txt` then
`func azure functionapp publish <name>`. Torch makes the package large; for the hackathon the local
host plus tunnel is fine.
