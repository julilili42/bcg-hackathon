"""Thin Twilio ConversationRelay adapter over the same engine as POST /interact."""
import asyncio
import hashlib
import hmac
import logging
import os
import re
from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from graph import handle_turn
from knowledge import utcnow

router = APIRouter()
WELCOME = (
    "Welcome to WaterLine, an AI assistant for fictional demo water points. "
    "Reports you share are stored and reused as unverified community information. "
    "Please say the water point and village with each question or report."
)


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
        welcome_greeting=WELCOME, welcome_greeting_interruptible="none",
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

    async def process_turns():
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
            if not closed and generation == output_generation:
                # Twilio supports SSML. Escape model text so sources cannot inject speech markup.
                spoken = escape(answer.replace("**", "").replace("`", ""))
                try:
                    await websocket.send_json({"type": "text", "token": spoken, "last": True,
                                               "interruptible": True, "preemptible": True})
                except (WebSocketDisconnect, RuntimeError, OSError):
                    pass

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
            elif kind == "prompt" and message.get("last") is True:
                text = message.get("voicePrompt")
                if not isinstance(text, str) or len(text) > 5000:
                    await websocket.close(code=1008)
                    break
                if not text.strip():
                    continue
                turn += 1
                generation += 1
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
        # Finish already received final turns even on hangup. Threaded Qdrant writes
        # cannot be safely cancelled; suppress output instead of rolling back facts.
        await queue.put(None)
        await worker
