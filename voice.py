"""Thin Twilio ConversationRelay adapter over the same engine as POST /interact."""
import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
from time import monotonic
from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from graph import handle_turn
from knowledge import utcnow
from speech import SpeechRequest, create_speech, spoken_text

router = APIRouter()
# Transient playback only: random capability URLs, five-minute expiry, at most 64 clips.
# Use one API worker for this small demo so the media GET shares the same memory.
AUDIO_TTL = 300
AUDIO_LIMIT = 64
_audio_clips: dict[str, tuple[float, bytes]] = {}


def prune_audio():
    now = monotonic()
    for clip_id, (expires, _) in list(_audio_clips.items()):
        if expires <= now:
            _audio_clips.pop(clip_id, None)


def cache_audio(content):
    prune_audio()
    while len(_audio_clips) >= AUDIO_LIMIT:
        _audio_clips.pop(next(iter(_audio_clips)))
    clip_id = secrets.token_urlsafe(32)
    _audio_clips[clip_id] = (monotonic() + AUDIO_TTL, content)
    return clip_id


@router.api_route("/twilio/audio/{clip_id}.mp3", methods=["GET", "HEAD"], include_in_schema=False)
async def call_audio(clip_id: str):
    # Twilio fetches media by URL; possession of the unguessable, expiring URL grants access.
    prune_audio()
    clip = _audio_clips.get(clip_id)
    if clip is None:
        raise HTTPException(404, "Audio clip unavailable or expired.")
    return Response(clip[1], media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

WELCOME = "Hey WaterLine here, how can i help you?"


def configuration():
    keys = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL")
    values = [os.getenv(key, "").strip() for key in keys]
    missing = [key for key, value in zip(keys, values) if not value]
    if missing:
        raise HTTPException(503, "Configure " + ", ".join(missing) + " in .env and restart.")
    account, token, base = values
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise HTTPException(503, "PUBLIC_BASE_URL must be your public HTTPS origin, with no path or query.")
    return account, token, base.rstrip("/")


@router.post("/twilio/voice")
async def incoming_call(request: Request):
    account, token, base = configuration()
    form = await request.form(max_files=0, max_fields=100)
    url = base + "/twilio/voice"
    if request.url.query:
        url += "?" + request.url.query
    if not RequestValidator(token).validate(url, form, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "Invalid Twilio signature.")
    if form.get("AccountSid") != account:
        raise HTTPException(403, "Unexpected Twilio account.")
    response = VoiceResponse()
    response.connect().conversation_relay(
        url=base.replace("https://", "wss://", 1) + "/twilio/ws",
        # Azure greeting is sent as media after WebSocket setup; Google is a failure fallback.
        language="en-US", tts_provider="Google", voice="en-US-Journey-O",
        transcription_provider="Deepgram", speech_model="nova-3-general",
        interruptible="speech", report_input_during_agent_speech="speech",
        speech_timeout="1200", hints="Alero,Lumwa,Palaro,borehole,clinic",
    )
    response.hangup()
    return Response(str(response), media_type="application/xml")


def valid_socket_signature(token, base, signature, query=""):
    # Validate the configured public origin, never an untrusted proxy Host header.
    # HTTP upgrade and WSS URL representations are both used by voice handshakes.
    validator = RequestValidator(token)
    suffix = "?" + query if query else ""
    return any(validator.validate(origin + path + suffix, {}, signature)
               for origin in (base, base.replace("https://", "wss://", 1))
               for path in ("/twilio/ws", "/twilio/ws/"))


@router.websocket("/twilio/ws")
async def conversation(websocket: WebSocket):
    try:
        account, token, base = configuration()
    except HTTPException:
        await websocket.close(code=1008)
        return
    if not valid_socket_signature(token, base, websocket.headers.get("x-twilio-signature", ""), websocket.url.query):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        setup = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if (not isinstance(setup, dict) or setup.get("type") != "setup"
                or setup.get("accountSid") != account
                or not re.fullmatch(r"CA[0-9a-fA-F]{32}", str(setup.get("callSid", "")))):
            await websocket.close(code=1008)
            return
    except (TimeoutError, ValueError):
        await websocket.close(code=1008)
        return
    except WebSocketDisconnect:
        return

    call_sid = setup["callSid"]
    # Call-scoped provenance: never forward or persist the caller's phone number.
    user_id = "caller-" + hmac.new(token.encode(), call_sid.encode(), hashlib.sha256).hexdigest()[:24]
    del setup
    queue = asyncio.Queue(maxsize=4)
    generation = 0
    turn = 0
    closed = False

    speech_task = None
    speech_interruptible = True

    async def send_spoken(answer, expected_generation=None, interruptible=True):
        nonlocal speech_task, speech_interruptible
        if closed or (expected_generation is not None and generation != expected_generation):
            return
        spoken = spoken_text(answer)
        clip = None
        try:
            speech_interruptible = interruptible
            speech_task = asyncio.create_task(create_speech(SpeechRequest(text=spoken)))
            response = await speech_task
            clip = response.body
        except asyncio.CancelledError:
            # Only the speech request was cancelled; never cancel a committed/ongoing report.
            return
        except Exception as exc:
            logging.error("Azure phone speech failed (%s); using fallback voice", type(exc).__name__)
        finally:
            speech_task = None
        if closed or (expected_generation is not None and generation != expected_generation):
            return
        if clip:
            clip_id = cache_audio(clip)
            payload = {"type": "play", "source": f"{base}/twilio/audio/{clip_id}.mp3", "loop": 1,
                       "interruptible": interruptible, "preemptible": interruptible}
        else:
            # Keep the call usable during an Azure outage; this uses the configured fallback TTS.
            payload = {"type": "text", "token": escape(spoken), "last": True,
                       "interruptible": interruptible, "preemptible": interruptible}
        try:
            await websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    async def process_turns():
        await send_spoken(WELCOME, interruptible=False)
        while True:
            item = await queue.get()
            if item is None:
                return
            message, turn_number, received_at, output_generation = item
            try:
                result = await handle_turn(message, user_id, f"twilio:{call_sid}:{turn_number}", received_at)
                answer = result["answer"]
            except Exception as exc:
                # Exception messages can contain provider request bodies; do not log transcripts.
                logging.error("Phone turn failed (%s), turn=%s", type(exc).__name__, turn_number)
                answer = "I couldn't complete that request. Your report may already be saved. Please try again later."
            await send_spoken(answer, expected_generation=output_generation)

    worker = asyncio.create_task(process_turns())
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.close(code=1008)
                break
            kind = message.get("type")
            if kind == "interrupt":
                # Twilio stops playback. Suppress unsent output, without cancelling writes.
                generation += 1
                if speech_task is not None and speech_interruptible:
                    speech_task.cancel()
            elif kind == "prompt" and message.get("last") is True:
                text = message.get("voicePrompt")
                if not isinstance(text, str) or len(text) > 5000:
                    await websocket.close(code=1008)
                    break
                if not text.strip():
                    continue
                turn += 1
                generation += 1
                if speech_task is not None and speech_interruptible:
                    speech_task.cancel()
                try:
                    queue.put_nowait((text, turn, utcnow(), generation))
                except asyncio.QueueFull:
                    await websocket.close(code=1013)
                    break
            elif kind == "error":
                logging.error("Twilio reported a ConversationRelay error; inspect Twilio's call debugger.")
                await websocket.close(code=1011)
                break
            elif kind == "setup":
                await websocket.close(code=1008)
                break
            # Partial prompts, speaker events and DTMF are never submitted as facts.
    except WebSocketDisconnect:
        pass
    except ValueError:
        await websocket.close(code=1008)
    finally:
        closed = True
        if speech_task is not None:
            speech_task.cancel()
        # Finish already received final turns even on hangup. Threaded Qdrant writes
        # cannot be safely cancelled; suppress output instead of rolling back facts.
        await queue.put(None)
        await worker
