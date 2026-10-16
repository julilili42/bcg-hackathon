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
./tunnel.sh                               # second terminal: public URL + Twilio now sends calls/SMS to YOUR machine
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
| `tunnel.sh` | starts a cloudflared tunnel and calls `set_webhooks.sh` with its URL |
| `set_webhooks.sh` | points the Twilio number and the browser phone at any public URL (tunnel or Azure) |
| `phone/` | browser phone for the pitch: real Twilio call from the laptop, photo of a Nokia 3310, live database beside it |

## Run locally

```bash
uv sync                          # Python 3.12 venv + deps
uv run download_models.py        # ~300 MB, once. Without it: Twilio's own voice (English only)
uv run brain.py && uv run tts.py # self-checks
cp local.settings.json.example local.settings.json   # fill in Twilio values
func start                       # http://localhost:7071  (uses .venv)
./smoke.sh                       # second terminal
```

Public URL for a real phone: `./tunnel.sh` starts cloudflared and points the Twilio number at it.
Quick tunnels die after a while; "We're sorry, an application error has occurred" on the phone
means: run `./tunnel.sh` again. Only one machine can own the webhooks at a time.

## Browser phone (for the pitch)

`http://localhost:7071/api/phone` shows a feature phone in the browser. The green key places a
**real** call through Twilio's Voice SDK (WebRTC): Twilio hits the same `/api/voice` webhook as a
phone call, the laptop microphone is the handset, the laptop speakers play the Swahili/English
answer, and the panel next to the phone shows what was understood and answered. Digit keys send
DTMF during the call (2 = English). Keyboard works too: digits, Enter = call, Esc = hang up.

One-time setup (creates a Twilio API key and a TwiML App, writes their ids into `local.settings.json`):

```bash
uv run phone/setup.py
./tunnel.sh            # or ./set_webhooks.sh <url>: also points the TwiML App at your host
```

Needs: microphone permission in the browser, and a network that allows WebRTC (test the venue
Wi-Fi beforehand). Fallback is always a real phone calling the number.

The chassis is a photo of a real Nokia 3310:
[Nokia 3310 Blue R7309170 (retouch).png](https://commons.wikimedia.org/wiki/File:Nokia_3310_Blue_R7309170_(retouch).png)
from Wikimedia Commons, Free Art License. The LCD and the key hit areas are HTML positioned in
percent of the photo (measured by colour detection, see git history for the script). LCD font:
Nokia Cellphone FC (Zeh Fernando, free for personal use). The right side is the live database:
water points with status and age, plus the last calls, refreshed every 2 s.

## Settings (`local.settings.json` / Azure App Settings)

| Key | |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | from console.twilio.com |
| `TWILIO_VALIDATE` | `1` in Azure: only signed Twilio requests. `0` locally for smoke.sh |
| `ANTHROPIC_API_KEY` | optional; `brain.py` then uses Claude Opus 5.5 (effort low, ~2 s). Without it: keyword matching |
| `SQL_CONN` | optional; without it SQLite `events.db` |
| `TWILIO_API_KEY`, `TWILIO_API_SECRET`, `TWILIO_APP_SID`, `TWILIO_NUMBER` | browser phone, written by `phone/setup.py` |

## Call flow

1. Greeting in Swahili: say the water point and its state. Press 2 for English.
2. Twilio transcribes with Google chirp_3 (`sw-KE` or `en-US`; chirp_3 has no `sw-TZ`, same spoken language). `brain.reply()` asks Claude for `{point, status, lang}`
   (loose name matching survives speech-recognition errors), sets `ok|broken|empty` if the caller
   reported, and answers with the nearest working point and walking minutes. SMS answers in the
   language the message was written in.
3. Reply spoken with MMS-TTS (`facebook/mms-tts-swh` / `-eng`), then hang up.

Why speech-to-text is Twilio's and not a local model: Twilio Gather with chirp_3 supports Swahili out of the box and
Whisper-small is weak on Swahili. Text-to-speech is local because Twilio has no Swahili voice.

## Deploy to Azure

Function App (Linux, Python 3.12) + Azure SQL with `schema.sql`. `uv export > requirements.txt` then
`func azure functionapp publish <name>`. Torch makes the package large; for the hackathon the local
host plus tunnel is fine.
