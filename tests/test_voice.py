"""Signed Twilio protocol tests; no real calls, phone numbers, or API charges."""
import asyncio
import threading
from datetime import datetime
from unittest.mock import AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from fastapi.responses import Response
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

import app as api
import voice

BASE = "https://waterline.example"
ACCOUNT = "AC" + "1" * 32
CALL = "CA" + "2" * 32
TOKEN = "synthetic-twilio-test-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", ACCOUNT)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setattr(api, "initialize", lambda: None)
    async def synthesize(request):
        return Response(b"MP3" + request.text.encode(), media_type="audio/mpeg")
    monkeypatch.setattr(voice, "create_speech", AsyncMock(side_effect=synthesize))
    voice._audio_clips.clear()
    with TestClient(api.app) as client:
        yield client


def signature(url, params=None):
    return {"X-Twilio-Signature": RequestValidator(TOKEN).compute_signature(url, params or {})}


def setup():
    return {"type": "setup", "callSid": CALL, "accountSid": ACCOUNT,
            "from": "+15555550123", "to": "+15555550456"}


def prompt(text, last=True):
    return {"type": "prompt", "voicePrompt": text, "last": last}



def begin(ws):
    ws.send_json(setup())
    greeting = ws.receive_json()
    assert greeting["type"] == "play"
    assert greeting["interruptible"] is False and greeting["preemptible"] is False
    return greeting


def spoken(client, message):
    if message["type"] == "text":
        return message["token"]
    assert message["type"] == "play"
    assert message["source"].startswith(BASE + "/twilio/audio/")
    response = client.get(message["source"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    return response.content[3:].decode()

def test_signed_incoming_call_twiml_and_public_origin(client):
    data = {"AccountSid": ACCOUNT, "CallSid": CALL, "From": "+15555550123"}
    response = client.post("/twilio/voice", data=data, headers=signature(BASE + "/twilio/voice", data))
    assert response.status_code == 200
    relay = ElementTree.fromstring(response.text).find("Connect/ConversationRelay")
    assert relay.attrib["url"] == "wss://waterline.example/twilio/ws"
    assert "welcomeGreeting" not in relay.attrib  # Azure greeting is sent through the WebSocket.
    assert relay.attrib["reportInputDuringAgentSpeech"] == "speech"
    assert "15555550123" not in response.text
    assert client.post("/twilio/voice", data=data).status_code == 403
    # A valid signature for the wrong host or an altered form cannot authenticate.
    assert client.post("/twilio/voice", data=data, headers=signature("https://evil.example/twilio/voice", data)).status_code == 403
    assert client.post("/twilio/voice", data={**data, "CallSid": "tampered"}, headers=signature(BASE + "/twilio/voice", data)).status_code == 403


def test_missing_twilio_config_leaves_text_endpoint_available(client, monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN")
    assert client.post("/twilio/voice").status_code == 503
    monkeypatch.setattr(api, "handle_turn", AsyncMock(return_value={"answer": "text still works"}))
    assert client.post("/interact", json={"message": "Working?"}).status_code == 200


def test_socket_requires_valid_signature_and_setup(client, monkeypatch):
    handler = AsyncMock()
    monkeypatch.setattr(voice, "handle_turn", handler)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/twilio/ws"):
            pass
    with client.websocket_connect("/twilio/ws", headers=signature("wss://waterline.example/twilio/ws")) as ws:
        ws.send_json(prompt("Skip setup"))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    handler.assert_not_called()


def test_final_transcripts_reuse_core_and_unique_turn_ids(client, monkeypatch):
    handler = AsyncMock(return_value={"answer": "An unverified **community report** <source>."})
    monkeypatch.setattr(voice, "handle_turn", handler)
    with client.websocket_connect("/twilio/ws", headers=signature("wss://waterline.example/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("provisional report", last=False))
        ws.send_json(prompt("   "))
        ws.send_json(prompt("The Alero clinic pump is broken."))
        response = ws.receive_json()
        assert response["type"] == "play"
        assert response["interruptible"] and response["preemptible"] and response["loop"] == 1
        assert spoken(client, response) == "An unverified community report <source>."
        ws.send_json(prompt("Is the Alero school borehole working?"))
        ws.receive_json()
    assert handler.await_count == 2
    first, second = [call.args for call in handler.await_args_list]
    assert first[0] == "The Alero clinic pump is broken."
    assert first[1].startswith("caller-") and first[1] == second[1]
    assert first[2] == f"twilio:{CALL}:1" and second[2] == f"twilio:{CALL}:2"
    assert datetime.fromisoformat(first[3]).tzinfo is not None
    assert all("15555550123" not in str(args) for args in (first, second))


def test_interrupt_suppresses_unsent_answer_but_finishes_report(client, monkeypatch):
    started, second_received, release = threading.Event(), threading.Event(), threading.Event()
    completed = []
    clock_calls = 0

    def clock():
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 2:
            second_received.set()
        return "2026-10-16T08:30:00Z"

    async def handle(message, *args, **kwargs):
        if message == "first report":
            started.set()
            assert await asyncio.to_thread(release.wait, 3)
        completed.append(message)
        return {"answer": message + " answer"}

    monkeypatch.setattr(voice, "utcnow", clock)
    monkeypatch.setattr(voice, "handle_turn", handle)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("first report"))
        assert started.wait(3)
        ws.send_json({"type": "interrupt", "utteranceUntilInterrupt": "part of an answer"})
        ws.send_json(prompt("second question"))
        assert second_received.wait(3)
        release.set()
        assert spoken(client, ws.receive_json()) == "second question answer"
    assert completed == ["first report", "second question"]


def test_hangup_finishes_accepted_turn_without_speaking(client, monkeypatch):
    started, release, completed = threading.Event(), threading.Event(), threading.Event()

    async def handle(*args):
        started.set()
        assert await asyncio.to_thread(release.wait, 3)
        completed.set()
        return {"answer": "saved"}

    monkeypatch.setattr(voice, "handle_turn", handle)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("The Alero clinic pump is broken."))
        assert started.wait(3)
        ws.send({"type": "websocket.disconnect", "code": 1000})
        release.set()
        assert completed.wait(3)


def test_core_error_gives_spoken_failure_and_call_can_continue(client, monkeypatch):
    handler = AsyncMock(side_effect=[RuntimeError("private internal error"), {"answer": "Next answer"}])
    monkeypatch.setattr(voice, "handle_turn", handler)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("report"))
        response = ws.receive_json()
        assert "may already be saved" in spoken(client, response)
        assert "private" not in spoken(client, response)
        ws.send_json(prompt("question"))
        assert spoken(client, ws.receive_json()) == "Next answer"
        ws.send_json({"type": "error", "description": "provider error"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_greeting_and_reply_use_same_azure_voice_and_expiring_media(client, monkeypatch):
    monkeypatch.setattr(voice, "handle_turn", AsyncMock(return_value={"answer": "A pump was reported broken; unverified."}))
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        greeting = begin(ws)
        assert spoken(client, greeting) == voice.WELCOME
        ws.send_json(prompt("Is the Alero clinic pump working?"))
        reply = ws.receive_json()
        assert spoken(client, reply) == "A pump was reported broken; unverified."
        assert all(call.args[0].voice == "en-US-AvaMultilingualNeural" for call in voice.create_speech.await_args_list)
        assert client.head(reply["source"]).status_code == 200
        assert client.get(reply["source"]).headers["cache-control"] == "no-store"
    future = voice.monotonic() + voice.AUDIO_TTL + 1
    monkeypatch.setattr(voice, "monotonic", lambda: future)
    assert client.get(reply["source"]).status_code == 404
    assert not voice._audio_clips


def test_outbound_native_greeting_context_and_session_isolation(client, monkeypatch):
    import infrastructure as db
    monkeypatch.setattr(db, "get_pipe_by_id", lambda _: dict(name="Alero school borehole", village="Alero"))
    opening = "Hey, WaterLine here, your AI assistant. Alero school borehole is reported broken, unverified."
    handler = AsyncMock(side_effect=[
        {"answer": "The Alero clinic hand pump is reported working.", "reports": []},
        {"answer": "Thanks, recorded as unverified.", "reports": [{"applied_to_current_status": True, "qdrant_indexed": True}]},
        {"answer": "A fresh conversation.", "reports": []}])
    monkeypatch.setattr(voice, "handle_turn", handler)
    parameters = {"waterline_mode": "outbound", "opening_message": opening,
        "opening_asset_id": "ff50877c-99aa-5dbb-a163-0a1d6b643a50"}
    headers = signature(BASE + "/twilio/ws")
    with client.websocket_connect("/twilio/ws", headers=headers) as ws:
        ws.send_json({**setup(), "customParameters": parameters})
        ws.send_json(prompt("partial", last=False))
        ws.send_json(prompt("Yes, where else can I go?"))
        first = ws.receive_json()
        # No duplicate greeting or audio synthesis: first WebSocket output is the agent answer.
        assert first["type"] == "text" and first["last"] is True
        assert "clinic" in first["token"]
        ws.send_json(prompt("The water point you just suggested is also broken."))
        assert "recorded" in ws.receive_json()["token"]
    assert handler.await_count == 2
    first_call, second_call = handler.await_args_list
    assert first_call.args[0] == "Yes, where else can I go?"
    assert first_call.kwargs["context"][0]["content"] == opening
    assert any(m["content"] == "The Alero clinic hand pump is reported working." for m in second_call.kwargs["context"])
    assert all("+1555555" not in str(call) for call in handler.await_args_list)
    voice.create_speech.assert_not_awaited()
    with client.websocket_connect("/twilio/ws", headers=headers) as ws:
        ws.send_json({**setup(), "callSid": "CA" + "3" * 32, "customParameters": parameters})
        ws.send_json(prompt("What about it?"))
        ws.receive_json()
    fresh = handler.await_args_list[-1]
    assert not any("clinic" in m["content"] for m in fresh.kwargs["context"])
    assert fresh.args[1] != first_call.args[1]


def test_audio_cache_is_bounded_and_urls_contain_no_transcripts(client, monkeypatch):
    monkeypatch.setattr(voice, "AUDIO_LIMIT", 2)
    first = voice.cache_audio(b"first")
    second = voice.cache_audio(b"second")
    third = voice.cache_audio(b"third")
    assert len(voice._audio_clips) == 2
    assert client.get(f"/twilio/audio/{first}.mp3").status_code == 404
    assert client.get(f"/twilio/audio/{second}.mp3").content == b"second"
    assert client.get(f"/twilio/audio/{third}.mp3").content == b"third"
    assert len(third) >= 40


def test_azure_failure_uses_spoken_fallback_without_losing_answer(client, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(voice, "handle_turn", AsyncMock(return_value={"answer": "Your unverified report was saved."}))
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        monkeypatch.setattr(voice, "create_speech", AsyncMock(side_effect=HTTPException(503, "synthetic Azure outage")))
        ws.send_json(prompt("The Alero clinic pump is broken."))
        reply = ws.receive_json()
        assert reply["type"] == "text" and "report was saved" in reply["token"]
        assert "synthetic Azure outage" not in reply["token"]


def test_interrupt_during_azure_generation_discards_audio_and_processes_next_turn(client, monkeypatch):
    started = threading.Event()
    cancelled = threading.Event()
    async def synthesize(request):
        if request.text == "first answer":
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return Response(b"MP3" + request.text.encode(), media_type="audio/mpeg")
    monkeypatch.setattr(voice, "create_speech", AsyncMock(side_effect=synthesize))
    handler = AsyncMock(side_effect=[{"answer": "first answer"}, {"answer": "second answer"}])
    monkeypatch.setattr(voice, "handle_turn", handler)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("first report"))
        assert started.wait(3)
        ws.send_json({"type": "interrupt"})
        ws.send_json(prompt("second question"))
        assert spoken(client, ws.receive_json()) == "second answer"
        assert cancelled.wait(3)
    assert handler.await_count == 2
    assert not any(content == b"MP3first answer" for _, content in voice._audio_clips.values())


def test_hangup_cancels_only_pending_speech(client, monkeypatch):
    started, cancelled = threading.Event(), threading.Event()
    async def synthesize(request):
        if request.text == "Saved report answer":
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return Response(b"MP3" + request.text.encode(), media_type="audio/mpeg")
    handler = AsyncMock(return_value={"answer": "Saved report answer"})
    monkeypatch.setattr(voice, "handle_turn", handler)
    monkeypatch.setattr(voice, "create_speech", AsyncMock(side_effect=synthesize))
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        begin(ws)
        ws.send_json(prompt("The Alero clinic pump is broken."))
        assert started.wait(3)
        ws.send({"type": "websocket.disconnect", "code": 1000})
        assert cancelled.wait(3)
    assert handler.await_count == 1
    assert not any(content == b"MP3Saved report answer" for _, content in voice._audio_clips.values())
