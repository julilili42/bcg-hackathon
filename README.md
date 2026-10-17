# WaterLine

One report helps the next village.

## Terminal-triggered outbound demo call

For a prepared news-first scenario, run `python seed_outbound_demo.py` and set
`DEMO_OPENING_PIPE_ID` to its printed school borehole UUID. The opening announces its
reported failure and suggests a working alternative selected from current database reports.
Follow-up access and maintenance details are retrieved from Qdrant. See the proactive phone
scenario in [DEMO_PROMPTS.md](DEMO_PROMPTS.md); no conversation is scripted or stored.

This adds outbound calls to the existing agent; it does not change the database schema or
replace the inbound Azure voice interface. No additional dependencies are required.

Configure these in your local `.env` (keep real numbers and keys out of source control):

```env
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
PUBLIC_BASE_URL=https://your-current-tunnel.example
DEMO_CALLEE_NUMBER=
DEMO_ALLOWED_NUMBERS=
DEMO_OPENING_PIPE_ID=
DEMO_OPENING_MESSAGE=
TWILIO_RELAY_TTS_PROVIDER=Google
TWILIO_RELAY_VOICE=
VOICE_DEBUG_TRANSCRIPTS=0
```

Use E.164 format for both phone numbers. Put the explicitly consenting recipient in both
`DEMO_CALLEE_NUMBER` and the comma-separated `DEMO_ALLOWED_NUMBERS` allowlist. The sender
must be your voice-capable Twilio number. Existing Anthropic, PostgreSQL, and Qdrant
configuration is reused. Trial accounts require a verified recipient; destination countries
must be enabled in Twilio Voice Geographic Permissions.

Leave `DEMO_OPENING_PIPE_ID` blank for a brief AI introduction. To proactively announce an
existing water point's reported condition, set that variable to its PostgreSQL UUID.
For the seeded school borehole, find it with:

```sh
.venv/bin/python -c 'import infrastructure as db; print(db.resolve_pipe("Alero school borehole", "Alero")["pipe"]["id"])'
```

The console reads the latest PostgreSQL record before dialing; it does
not seed a failure, invent a repair, or save its own introduction as a resident report.
It identifies WaterLine as AI and describes the status as unverified and potentially outdated.
`DEMO_OPENING_MESSAGE` optionally supplies the default introduction's message when no asset
is selected. It follows the fixed AI introduction; only put truthful demo content there.

Start the existing backend and tunnel in separate terminals:

```sh
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
cloudflared tunnel --url http://localhost:8000
```

Set `PUBLIC_BASE_URL` to the current HTTPS tunnel origin and restart the backend after
changing it. Twilio must be able to reach `/twilio/ws` over WSS. The outbound console uses
inline TwiML and the existing signed WebSocket; it requires no new webhook or dialing endpoint.

In another terminal:

```sh
.venv/bin/python scripts/demo_call.py
```

Press **c** (no Enter required on macOS/Linux). Only this action requests a call. The
allowlisted recipient's phone should ring; answer to hear the opening. Ask “Where else can
I go?” or report “It is working again now.” The same LangGraph resolves references using
bounded, call-local conversation context and applies the existing timestamp, PostgreSQL and
Qdrant rules. Each call starts with fresh context. Text callers can also pass context to the
shared `handle_turn(..., context=[...])` function; no separate phone agent exists.

The console masks the recipient, prints the real Call SID, and polls actual provider status.
Repeated **c** presses are blocked while active. A local lock prevents two consoles for the
same account; a provider lookup also catches an existing call after a restart. A timeout
while creating a call blocks another attempt because the first request may have succeeded.
Press **q** to quit monitoring; it does not hang up an existing call. End the call on the phone.
There are no startup calls, redial loops, recording, scheduling, or outbound HTTP endpoint.

Outbound speech uses Deepgram and native ConversationRelay TTS, with the existing Google
Journey voice as the default. To use ElevenLabs, set `TWILIO_RELAY_TTS_PROVIDER=ElevenLabs`
and `TWILIO_RELAY_VOICE` to a voice supported by your ConversationRelay configuration.
Azure still serves inbound calls and the browser demo. The opening is passed through
[`welcomeGreeting`](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay),
and the WebSocket sends each complete answer as a text token message. It does not send
a duplicate greeting after setup or implement a new audio pipeline. Logs distinguish a
configured greeting from confirmed playback; they do not claim it was heard.

Keep transcript logging off by default. For a local demonstration only, setting
`VOICE_DEBUG_TRANSCRIPTS=1` prints a limited user transcript to the backend terminal.
Ordinary backend logs include call/turn events and confirmed report/indexing counts.
Current navigation support is limited to known destination names and access landmarks:
there is no route calculation/publication service, so the agent does not claim a dashboard
route was sent. Infrastructure status changes still appear through the existing live dashboard.

Tests never dial real numbers:

```sh
.venv/bin/python -m pytest -q
RUN_BROWSER_SMOKE=1 .venv/bin/python -m pytest tests/test_browser_demo.py -q
RUN_POSTGRES_SMOKE=1 RUN_LIVE_LLM=1 .venv/bin/python -m pytest tests/test_infrastructure.py -k live_followups -s -q
```

The optional live-model rehearsal uses a temporary SQL schema and Qdrant collection; it
checks pronoun resolution, real report persistence/indexing and retained provenance without
placing a telephone call. A real end-to-end call requires the configured recipient to answer.

Text-first prototype with an optional Twilio phone adapter: a resident reports a change and asks a question in the same message. Another resident can immediately retrieve that report with dates and provenance. All included villages, assets and observations are **fictional synthetic demo data**, not verified Ugandan infrastructure.

## Run the infrastructure demo

Python 3.11+ is required (this change was tested with Python 3.14). The backend keeps the
existing Anthropic model, FastEmbed dense embeddings, and Qdrant BM25/RRF retrieval.
PostgreSQL owns registered assets and their current **reported** status. The Streamlit
dashboard reads PostgreSQL directly; its text form submits to the existing FastAPI endpoint.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# For a new installation only. Keep your existing .env if you already have one.
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env. Keep credentials out of git.
docker compose up -d
python infrastructure.py
python seed_infrastructure.py
python seed.py
python reindex.py
uvicorn app:app --reload
```

For the three-turn showcase, run `python seed_showcase.py` while the dashboard is open.
This adds six synthetic observations and six notices to the configured PostgreSQL database and
`water_knowledge` collection. Follow the first three prompts in [DEMO_PROMPTS.md](DEMO_PROMPTS.md).
The seed is idempotent; use `--run-id rehearsal-2` to append a fresh starting state for another run.

In a second terminal:

```sh
source .venv/bin/activate
streamlit run dashboard.py
```

Open http://localhost:8501. The **Infrastructure** tab shows totals, village/status filters,
colored statuses, an illustrative map, and an asset's complete report trail (up to 100 rows).
**Ask & report** accepts natural-language messages and shows extracted intent, persistence
outcomes, dates, and evidence. The infrastructure view checks SQL automatically every three seconds while the dashboard is open.
Only that view reruns, so unfinished text messages stay intact; there is no status cache.
New changes slide into a five-item activity feed, flash the summary metrics, and highlight
changed table rows for twelve seconds. Cards show the old and new **reported** status;
a historical report that leaves current status unchanged is labeled accordingly. Idle polls
do not create duplicate events or replay the animation. The initial load establishes a baseline,
and the activity feed covers this viewing session. Full report history remains in PostgreSQL.
Animations respect the browser's reduced-motion setting. Green means reported operation;
amber verification flags remain visible because community reports are unverified.

API documentation: http://localhost:8000/docs. The CLI remains available:
`python demo.py --interactive`. The fixed-clock `python demo.py` story is intended for a
fresh demo database; historical story timestamps will not overwrite newer live reports.

Database defaults: `postgresql://waterline:waterline@localhost:5433/waterline_live`.
PostgreSQL uses port 5433 to avoid a common local 5432 conflict. Change `DATABASE_URL`
for another deployment. The Compose password is for a local fictional demo only. If you
change `POSTGRES_PASSWORD`, also update `DATABASE_URL`; changing an environment variable
does not change the password in an already initialized database volume. Existing PostgreSQL
volumes also do not create a newly named database automatically; provision `waterline_live`
first if reusing a volume from an older setup. Schema initialization creates tables and
indexes without resetting records. Seeds use stable IDs and never reset newer statuses.

Qdrant must support server-side `Qdrant/bm25` inference (the Compose version is 1.15.5).
If port 6333 is occupied, use `QDRANT_PORT=6334 docker compose up -d` and set
`QDRANT_URL=http://localhost:6334` in `.env`; both backend and seed commands must use the
same endpoint. `WATERLINE_API_URL` configures the dashboard's backend URL (default
http://localhost:8000). Set `DATABASE_URL=` explicitly only to retain the previous
Qdrant-only CLI/API behavior; the new dashboard requires PostgreSQL.

## Live demonstration

See [DEMO_PROMPTS.md](DEMO_PROMPTS.md) for a spoken cross-user story and document, history, ambiguity, safety, and location scenarios.

1. Open Infrastructure, filter to Alero, and inspect **Alero school borehole**.
2. In Ask & report, send: **"The Alero School Borehole is broken today."**
   Watch Infrastructure: within about three seconds its reported status becomes broken. The report appears in history.
3. Send: **"The Alero School Borehole was repaired this afternoon and is working again."**
   The reported status updates automatically to operational, with both observations retained and
   verification still required. Use this phrase in the afternoon, or say **"is working again now"**.
4. Send: **"The Alero School Borehole was broken last week."**
   The historical observation is saved; the newer operational report stays current.
   If the observation time is too vague, the assistant asks for the time before changing status.
5. Send: **"The pipe near the school is broken."**
   The report is preserved, but the assistant asks which registered school asset you mean.
6. As demo-user-b, send: **"The Alero Market Water Point stopped working today. Where else can we go?"**
   The market report commits before retrieval. The answer uses SQL statuses for alternatives
   and Qdrant for supporting knowledge; the newly broken market is excluded as an operational option.
7. Ask: **"Which pipes in Alero are currently working?"**
   No reports are written. The answer uses the latest SQL state with dates and unverified labels.

Use new turn IDs for new observations. The dashboard generates these automatically and
retains an ID for retry after a network error. The API accepts `turn_id` for the same purpose,
generates a trusted UTC receipt time, and rejects client-provided receipt timestamps.

```sh
curl -X POST http://localhost:8000/interact \
  -H 'Content-Type: application/json' \
  -d '{"message":"The Alero Market Water Point stopped working today. Where else can we go?","user_id":"demo-user-a","turn_id":"live-demo-001"}'
```

## Persistence and recovery

`schema.sql` defines `pipes` and `pipe_reports`. `infrastructure.py` contains parameterized
SQL and deterministic entity matching against names, aliases, villages, and registered UUIDs.
A unique name match is required; fuzzy matches with similar candidates require clarification.
No report creates a physical asset. Unmatched and general knowledge reports are preserved.

Each fact gets a stable UUID from its turn ID and index. A transaction locks the matched pipe,
inserts the observation, and applies only a non-future observation at least as recent as the
current one. Explicit event times take precedence; clear present-tense observations may use
the receipt time, and ambiguous historical times do not change status. All community updates
require verification. Differing observations within one day are exposed as conflicts with dates.

After SQL commits, the report UUID becomes the Qdrant point UUID. Qdrant stores the original
message, normalized claim, and provenance links, without mirroring the current pipe table.
Successful indexing marks `qdrant_indexed=true`. On an indexing outage the report and SQL
status remain intact; the API explains that indexing is pending. Recover with:

```sh
python reindex.py
```

This retries unindexed reports, including fictional seed observations, and exits nonzero if
any remain failed. There is no shared transaction across SQL and Qdrant. If retrieval later
fails, the agent can answer using SQL alone and explicitly labels that limitation.

Limitations: entity matching is intentionally conservative; clarification does not automatically
attach a follow-up to the earlier unresolved report, so repeat the observation with its full
asset name. No background retries, authentication, status verification process, or claim of
water safety is provided. The 100-row asset history display is bounded for the demo. All
seed assets, coordinates, and reports are fictional. Existing optional phone/audio adapters
are preserved; the browser voice demo uses the same text endpoint without a phone call.

## Verify

```sh
python -m pytest -q
RUN_POSTGRES_SMOKE=1 python -m pytest tests/test_infrastructure.py -q
RUN_POSTGRES_SMOKE=1 RUN_QDRANT_SMOKE=1 python -m pytest -q
# Optional live Anthropic rehearsal (uses configured credentials):
RUN_POSTGRES_SMOKE=1 RUN_LIVE_LLM=1 python -m pytest tests/test_infrastructure.py::test_live_natural_language_rehearsal -q -s
```

Default tests run offline and skip database integration. PostgreSQL integration uses temporary
schemas in `TEST_DATABASE_URL` (default: the local `waterline_live` URL), seeds fictional assets,
and removes those schemas afterward. Combined SQL/Qdrant tests create and remove their own
temporary collections and exercise real dense and BM25 paths, RRF, report writes, and SQL
precedence. The legacy Qdrant smoke test idempotently seeds the configured collection and
removes its temporary report points. These tests mock the chat model unless `RUN_LIVE_LLM=1`.
The dashboard test runs Streamlit's actual AppTest and checks metrics after a SQL status change.
An optional Chrome test verifies that timed updates appear without a reload and preserve an unfinished message.

The SQL connection lifecycle follows [psycopg's transaction context documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
The table uses [Streamlit's dataframe API](https://docs.streamlit.io/develop/api-reference/data/st.dataframe).

## Talk to the agent in your browser

Start the API and dashboard normally, then click **🎙 Open voice demo** in the dashboard,
or open http://localhost:8000/demo directly. This is a separate page, so keep the dashboard
beside it to watch status changes appear automatically.

1. Click **Start conversation** and grant microphone permission.
2. Say the complete water point name and village, then pause. Finalized speech is sent automatically.
3. The orb changes from listening to thinking, then speaking. The assistant reads its answer aloud
   and listens for your next turn after playback finishes.
4. Use **Interrupt reply** to cut playback short and speak again, or **End conversation** to stop
   the microphone and voice playback. Ending a conversation never removes a report already saved.
5. The keyboard button opens a text composer. Sources remain available below each answer.
   **Voice & demo settings** includes a voice picker, demo resident, and toggles for hands-free
   operation and spoken replies. Turn hands-free off to review transcripts before sending.
6. **Hear last reply** replays the latest answer, including if automatic playback was blocked.
   The dashboard checks SQL every three seconds; no manual refresh is required.

Try: **"The Alero Market Water Point is broken now. Which other water points are working?"**
Only finalized speech is eligible for submission. Partial recognition and microphone errors
never save a report. Microphone capture stops while the assistant is thinking or speaking, then resumes after
playback in hands-free mode. Recognition errors and silence pause the conversation rather than
restarting the microphone in a loop. Failed requests retain the same turn ID for retry while the page
remains open. Audio playback cancellation does not roll back a saved report.

Spoken replies use **Azure Neural text to speech** in **Germany West Central**,
with **Ava Multilingual Neural** (`en-US-AvaMultilingualNeural`) as the default voice.
Choose Andrew or Sonia in voice settings to compare. Add the following to your local `.env`,
then restart Uvicorn and reload `/demo`:

```env
AZURE_SPEECH_ENDPOINT=https://germanywestcentral.api.cognitive.microsoft.com/
AZURE_SPEECH_KEY=your-azure-speech-resource-key
```

The provided Cognitive Services base URL identifies the region. The server maps it to
`https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1`, Azure's regional
speech synthesis endpoint. You may also set `AZURE_SPEECH_ENDPOINT` to that full URL directly.
Use a key from a Speech-enabled Azure resource in the same region.
See [Microsoft's regional REST API documentation](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

The key stays on the server. The browser sends the grounded answer to `POST /speech`,
which escapes it into SSML and returns MP3 audio. Replay reuses the latest clip for the same
text and voice within that page session. Interrupting or ending the conversation stops
playback and prevents late audio from starting. Missing credentials, quota limits, or
speech failures leave the text answer and saved reports intact. After correcting a speech
issue, click **Hear last reply**; it retries speech without submitting the water report again.
The UI identifies the voice as AI-generated. No additional Python dependency is required;
the endpoint uses the existing HTTP client. This path no longer uses `OPENAI_API_KEY`.

Speech input still uses browser
[SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).
Try Chrome on localhost or use HTTPS when hosting. Recognition may use the browser
vendor's online service; audio input should not be assumed to stay on-device or work
offline. WaterLine receives the finalized transcript. Typing remains available if the
browser does not support recognition. English is the demo language; disable hands-free
mode to correct place names before sending. The browser currently sends each turn without
conversation context, so include the asset name and village. Phone calls pass bounded
context to the same knowledge engine and can resolve unambiguous follow-ups.

Optional browser tests (microphone, Azure responses, and audio playback are simulated):

```sh
pip install playwright
# Tests use installed Google Chrome; no Playwright browser download is needed.
RUN_BROWSER_SMOKE=1 python -m pytest tests/test_browser_demo.py -q
RUN_POSTGRES_SMOKE=1 RUN_BROWSER_SMOKE=1 python -m pytest tests/test_infrastructure.py::test_dashboard_updates_in_browser_without_refresh -q
```

The automatic view uses [Streamlit fragments](https://docs.streamlit.io/develop/concepts/architecture/fragments).
This is polling with an approximately three-second delay, rather than immediate server push.

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

`knowledge.py` uses one active collection selected by `QDRANT_COLLECTION` (default `water_knowledge`), with named 384-dimensional dense vectors and IDF-enabled BM25. `cloud_inference=True` forwards BM25 document inference to Qdrant. Both filtered retrieval paths feed native RRF. PostgreSQL supplies registered assets' current reported status independently of semantic top-k. In legacy Qdrant-only mode, exact status-history scrolling retains the original 100-record bound.

## Test intent detection with an empty collection

Set `QDRANT_COLLECTION=water_knowledge_test` in `.env` and restart Uvicorn. Startup creates the collection and indexes if missing, without seeding it. Existing collections and reports are preserved. To get a fresh empty workspace later, choose a new collection name. All interfaces use the same selected collection. The API returns `knowledge_collection` so you can verify which one is active.

Use `/interact`, `demo.py --interactive`, or recorded audio for these checks:

| Message | Expected intent | Saved facts |
| --- | --- | --- |
| Is the Alero clinic pump working? | `query` | None; initially there is no evidence |
| The Alero clinic pump is broken. | `report` | One unverified report |
| The Alero school borehole is working. Is the Alero clinic pump working? | `both` | One school report, then retrieval for the clinic |

Inspect `interpretation.facts`, `interpretation.query`, `stored_fact_ids`, and `sources` in the response. The small fictional asset-name registry remains in the interpreter so it can match names; the selected Qdrant collection starts with no documents or status evidence.

For the original Qdrant-only empty-data test, explicitly set `DATABASE_URL=`. Do not run `seed.py`, the default canned `demo.py`, or `RUN_QDRANT_SMOKE=1`: those intentionally populate the selected collection. Set `QDRANT_COLLECTION=water_knowledge` and restart to return to your original seeded data.

`graph.py` runs `interpret → store_if_needed → retrieve_if_needed → respond`. One structured Anthropic model call extracts atomic facts and a separate question. Code resolves event/report chronology per asset and attribute, retains nearby contradictions, and removes private provenance from answer evidence. A second call phrases a grounded answer. Reports always remain unverified; a code-level safety gate refuses water-quality assurance without verified quality evidence. Qdrant preserves all history. Stable registry documents are not ranked by recency.

`seed.py` upserts 21 clearly synthetic records across six assets and three fictional village labels. It is safe to rerun. The CLI and HTTP API remain available alongside the optional phone adapter.

## Call WaterLine using Twilio

`voice.py` adds `POST /twilio/voice` (incoming-call TwiML) and `WebSocket /twilio/ws` (ConversationRelay). It invokes the **same `handle_turn()` as `/interact`**, without a loopback HTTP request. Twilio handles caller transcription and audio playback; the graph, Anthropic model and Qdrant collection are shared.
The greeting and agent replies now use the **same Azure Ava Multilingual Neural voice as the browser demo**.
Both voice interfaces open with “Hey WaterLine here, how can i help you?” Replies use short,
conversational sentences. Report identifiers and numeric dates stay in the source details;
spoken answers refer naturally to community reports and their freshness.
ConversationRelay does not accept Azure as a built-in `ttsProvider`, so the server synthesizes the
answer through the existing Azure function and sends a supported `play` media message with an
HTTPS MP3 URL. Google Journey remains configured only as a fallback if Azure synthesis fails.
See [Twilio's play media protocol](https://www.twilio.com/docs/voice/conversationrelay/websocket-messages#play-media-message).

The `/twilio/audio/<random-token>.mp3` URLs contain no transcript, caller number, or credentials.
Clips expire after five minutes and the in-memory cache is capped at 64 clips. Keep this demo
on **one Uvicorn worker**, so WebSocket generation and media retrieval share the same cache.
Your public tunnel must serve `/twilio/audio/` as well as `/twilio/voice` and `/twilio/ws`.
The webhook and WebSocket retain Twilio signature validation; media retrieval uses its
unguessable, short-lived URL because Twilio fetches the media as a separate request.
Configure `AZURE_SPEECH_KEY` and `AZURE_SPEECH_ENDPOINT` as described in the browser voice section.
No Twilio number/webhook change is needed if the existing public URL is unchanged.
If a temporary Cloudflare/ngrok hostname expires or stops resolving, restart the tunnel,
update `PUBLIC_BASE_URL` and the number's incoming-call webhook to the new public origin,
and restart the API. Both the WebSocket and the generated audio URLs must remain reachable.

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

7. After the greeting, say: **“The Alero clinic pump stopped working this morning. Is the Alero school borehole working?”** Then ask: **“Is the Alero clinic pump working?”** Full names remain useful when several water points are discussed; unambiguous follow-ups use the current call's bounded context. The current speech pilot is English (`en-US`); no local-language or accent accuracy is claimed.

Only `prompt` messages with `last: true` enter the graph. Each completed utterance gets its own stable `twilio:<callSid>:<turn_number>` ID and server receipt timestamp. The caller ID is call-scoped and HMAC-derived from the call identifier; caller phone numbers are not passed to the graph or stored in Qdrant. Community reports are saved and reused as unverified information.

The receiver continues listening while turns run in order. Interruptions and hangups suppress unsent speech, but let already accepted final turns finish so committed facts are retained. Connection state and the turn counter exist only for the current WebSocket connection; this prototype does not reconnect or recover call state after a server restart. Twilio performs speech interruption on its side. Answers are synthesized only after retrieval/resolution completes. The phone adapter sends
one Azure audio `play` message per completed answer. An interrupt cancels pending synthesis
and suppresses stale output, while accepted reports continue saving. The Azure greeting is
non-interruptible so the opening is not cut off; answer playback is interruptible and preemptible.
If Azure synthesis fails, a text message invokes ConversationRelay's fallback voice instead.

Both endpoints validate Twilio signatures against your configured public URL. Missing voice configuration disables the phone adapter without disabling `/interact`. Direct unsigned `curl` requests to `/twilio/voice` return 403 by design. If calls fail, check Twilio's call debugger: 64102 usually indicates an unreachable WSS route; 64110 indicates ConversationRelay is not enabled. A 403 often means the public URL or account Auth Token differs from the one Twilio is using. Update both `.env` and the number's webhook if the tunnel address changes.

The signed webhook/WebSocket tests run with `python -m pytest -q` and simulate final speech, partial speech, interruptions, hangups, and provider failures without making calls. A real phone test additionally requires your Twilio number, account configuration and live tunnel. Protocol reference: [Twilio ConversationRelay messages](https://www.twilio.com/docs/voice/conversationrelay/websocket-messages).
