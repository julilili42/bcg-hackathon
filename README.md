# WaterLine

One report helps the next village.

Text-first prototype with an optional Twilio phone adapter: a resident reports a change and asks a question in the same message. Another resident can immediately retrieve that report with dates and provenance. All included villages, assets and observations are **fictional synthetic demo data**, not verified Ugandan infrastructure.

## Run

Python 3.12 is tested. Docker runs Qdrant; Anthropic API credentials enable live interpretation and answers.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in ANTHROPIC_API_KEY in .env; never commit credentials.
# ANTHROPIC_MODEL defaults to claude-sonnet-4-6; no Azure deployment is needed.
docker compose up -d
python seed.py
python demo.py
```

`demo.py` prints the fixed-clock four-turn story, interpretation, saved fact IDs, selected evidence, timestamps and answers. `python demo.py --interactive` accepts free text. Reports are stored and reused; use opaque demo IDs and synthetic observations. The seeded clock is October 16, 2026; old observations are not proof of a current condition.

For the API:

```sh
uvicorn app:app --reload
curl -X POST http://localhost:8000/interact \
  -H 'Content-Type: application/json' \
  -d '{"message":"The Alero clinic pump broke this morning. Is the school borehole working?","user_id":"demo-user-a","turn_id":"my-demo-turn-001"}'
```

Interactive API documentation: http://localhost:8000/docs. Reuse a turn ID when retrying the same message; use a new ID for a new observation. The API generates its own UTC receipt time and rejects client timestamps. The CLI uses the trusted `handle_turn()` function directly for fixed-clock rehearsals. An outage after writing may leave reports saved; retry with the same ID. Empty messages ask for clarification.

## Verify

```sh
python -m pytest -q
RUN_QDRANT_SMOKE=1 python -m pytest -q
```

Default tests mock external services. The integration test requires running Qdrant and downloads the FastEmbed model on first use. It exercises actual dense retrieval, server-side BM25, native RRF, idempotent writes and the graph's cross-user sharing loop. Only Anthropic chat calls are mocked. Live LLM quality requires credentials and a rehearsal with `python demo.py`; unit tests do not validate the model's interpretations.

## Test recorded audio locally, without a call

Record a short English message in Voice Memos or QuickTime and save/export it as M4A or WAV. Install the optional local transcription dependency:

```sh
source .venv/bin/activate
pip install -r requirements-audio.txt
```

With the server running (`uvicorn app:app --port 8000`), send the recording:

```sh
python audio_demo.py /path/to/message.m4a
```

`audio_demo.py` runs the local Whisper `base.en` model on CPU, prints the completed transcript, and sends it as JSON to the existing `/interact` endpoint. It displays the normal answer, intent and sources. Only the transcript is sent to WaterLine; the recording is not uploaded or stored by the API. The local model downloads on the first run, then is cached in `.cache/whisper`. No additional speech API key is needed. Transcription accuracy, especially place names, must be checked with real recordings.

To check transcription without storing a report, run `python audio_demo.py message.m4a --transcribe-only`. To hear the returned answer on macOS, add `--speak`; this uses the system voice, not Google/Twilio's voice. `--user-id demo-user-b` simulates another resident. Reuse `--turn-id YOUR_ID` when retrying the same recording, or use the automatically generated ID for a new message. `--url http://127.0.0.1:8000` selects the API origin.

This exercises local audio transcription and the live knowledge engine; the Twilio call transport and its speech providers are tested separately by calling the number.

## Implementation

`knowledge.py` uses one active collection selected by `QDRANT_COLLECTION` (default `water_knowledge`), with named 384-dimensional dense vectors and IDF-enabled BM25. `cloud_inference=True` forwards BM25 document inference to Qdrant. Both filtered retrieval paths feed native RRF. Exact status-history scrolling prevents the latest observation from disappearing below semantic top-k; it fails explicitly above the demo's 100-record bound.

## Test intent detection with an empty collection

Set `QDRANT_COLLECTION=water_knowledge_test` in `.env` and restart Uvicorn. Startup creates the collection and indexes if missing, without seeding it. Existing collections and reports are preserved. To get a fresh empty workspace later, choose a new collection name. All interfaces use the same selected collection. The API returns `knowledge_collection` so you can verify which one is active.

Use `/interact`, `demo.py --interactive`, or recorded audio for these checks:

| Message | Expected intent | Saved facts |
| --- | --- | --- |
| Is the Alero clinic pump working? | `query` | None; initially there is no evidence |
| The Alero clinic pump is broken. | `report` | One unverified report |
| The Alero school borehole is working. Is the Alero clinic pump working? | `both` | One school report, then retrieval for the clinic |

Inspect `interpretation.facts`, `interpretation.query`, `stored_fact_ids`, and `sources` in the response. The small fictional asset-name registry remains in the interpreter so it can match names; the selected Qdrant collection starts with no documents or status evidence.

For an empty-data test, do not run `seed.py`, the default canned `demo.py`, or `RUN_QDRANT_SMOKE=1`: those intentionally populate the selected collection. Set `QDRANT_COLLECTION=water_knowledge` and restart to return to your original seeded data.

`graph.py` runs `interpret → store_if_needed → retrieve_if_needed → respond`. One structured Anthropic model call extracts atomic facts and a separate question. Code resolves event/report chronology per asset and attribute, retains nearby contradictions, and removes private provenance from answer evidence. A second call phrases a grounded answer. Reports always remain unverified; a code-level safety gate refuses water-quality assurance without verified quality evidence. Qdrant preserves all history. Stable registry documents are not ranked by recency.

`seed.py` upserts 21 clearly synthetic records across six assets and three fictional village labels. It is safe to rerun. The CLI and HTTP API remain available alongside the optional phone adapter.

## Call WaterLine using Twilio

`voice.py` adds `POST /twilio/voice` (incoming-call TwiML) and `WebSocket /twilio/ws` (ConversationRelay). It invokes the **same `handle_turn()` as `/interact`**, without a loopback HTTP request. Twilio handles transcription and speech playback; the graph, Anthropic model and Qdrant collection are shared.

1. Create a [Twilio account](https://console.twilio.com/) and [get a phone number with Voice capability](https://www.twilio.com/docs/numbers-and-senders/phone-number-senders). In the Console, copy your **Account SID** and **Auth Token** to `.env`. Use the account Auth Token for webhook signature validation, not an API-key secret. Phone number availability and requirements depend on the country; review the number and call charges in Twilio before buying.
2. Complete [ConversationRelay onboarding](https://www.twilio.com/docs/voice/conversationrelay/onboarding). In Voice settings, enable/accept the Predictive and Generative AI/ML Features Addendum. ConversationRelay must be enabled on the account that owns the number.
3. Start the existing app:

```sh
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d
python seed.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

4. Create an [ngrok account and install its CLI](https://ngrok.com/docs/share-localhost/quickstart). On macOS, run the following in another terminal, replacing the token placeholder with your ngrok dashboard token:

```sh
brew install ngrok
ngrok config add-authtoken YOUR_NGROK_TOKEN
ngrok http 8000
```

5. Copy ngrok's **HTTPS forwarding address** into `PUBLIC_BASE_URL` in `.env`. The following values are placeholders; keep your existing Anthropic and Qdrant settings:

```env
TWILIO_ACCOUNT_SID=ACyour_account_sid
TWILIO_AUTH_TOKEN=your_account_auth_token
PUBLIC_BASE_URL=https://your-domain.ngrok-free.app
```

Use only the origin for `PUBLIC_BASE_URL`: no `/twilio/voice`, credentials, query, or fragment. Restart Uvicorn after changing `.env`. Keep Uvicorn and ngrok running. An HTTPS tunnel also carries the WSS connection; no separate WebSocket tunnel or certificate is needed.

6. Open your number's **Voice configuration** in Twilio. For **A call comes in**, choose **Webhook**, method **HTTP POST**, and enter:

```text
https://your-domain.ngrok-free.app/twilio/voice
```

Save, then call that Twilio number from your phone. If your Console uses TwiML Apps instead, set the app's Voice request URL to this same endpoint and assign that app to the number.

7. After the greeting, say: **“The Alero clinic pump stopped working this morning. Is the Alero school borehole working?”** Then ask: **“Is the Alero clinic pump working?”** Name the asset and village in each utterance; this adapter does not add conversation memory or resolve cross-turn pronouns. The current speech pilot is English (`en-US`); no local-language or accent accuracy is claimed.

Only `prompt` messages with `last: true` enter the graph. Each completed utterance gets its own stable `twilio:<callSid>:<turn_number>` ID and server receipt timestamp. The caller ID is call-scoped and HMAC-derived from the call identifier; caller phone numbers are not passed to the graph or stored in Qdrant. The greeting discloses that reports are stored and reused. User reports remain unverified.

The receiver continues listening while turns run in order. Interruptions and hangups suppress unsent speech, but let already accepted final turns finish so committed facts are retained. Connection state and the turn counter exist only for the current WebSocket connection; this prototype does not reconnect or recover call state after a server restart. Twilio performs speech interruption on its side. Answers are sent only after retrieval/resolution completes, as a single final text message.

Both endpoints validate Twilio signatures against your configured public URL. Missing voice configuration disables the phone adapter without disabling `/interact`. Direct unsigned `curl` requests to `/twilio/voice` return 403 by design. If calls fail, check Twilio's call debugger: 64102 usually indicates an unreachable WSS route; 64110 indicates ConversationRelay is not enabled. A 403 often means the public URL or account Auth Token differs from the one Twilio is using. Update both `.env` and the number's webhook if the tunnel address changes.

The signed webhook/WebSocket tests run with `python -m pytest -q` and simulate final speech, partial speech, interruptions, hangups, and provider failures without making calls. A real phone test additionally requires your Twilio number, account configuration and live tunnel. Protocol reference: [Twilio ConversationRelay messages](https://www.twilio.com/docs/voice/conversationrelay/websocket-messages).
