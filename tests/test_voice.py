"""Signed Twilio protocol tests; no real calls, phone numbers, or API charges."""
import asyncio
import threading
from datetime import datetime
from unittest.mock import AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
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
    with TestClient(api.app) as client:
        yield client


def signature(url, params=None):
    return {"X-Twilio-Signature": RequestValidator(TOKEN).compute_signature(url, params or {})}


def setup():
    return {"type": "setup", "callSid": CALL, "accountSid": ACCOUNT,
            "from": "+15555550123", "to": "+15555550456"}


def prompt(text, last=True):
    return {"type": "prompt", "voicePrompt": text, "last": last}


def test_signed_incoming_call_twiml_and_public_origin(client):
    data = {"AccountSid": ACCOUNT, "CallSid": CALL, "From": "+15555550123"}
    response = client.post("/twilio/voice", data=data, headers=signature(BASE + "/twilio/voice", data))
    assert response.status_code == 200
    relay = ElementTree.fromstring(response.text).find("Connect/ConversationRelay")
    assert relay.attrib["url"] == "wss://waterline.example/twilio/ws"
    assert "stored and reused" in relay.attrib["welcomeGreeting"]
    assert relay.attrib["welcomeGreetingInterruptible"] == "none"
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
        ws.send_json(setup())
        ws.send_json(prompt("provisional report", last=False))
        ws.send_json(prompt("   "))
        ws.send_json(prompt("The Alero clinic pump is broken."))
        response = ws.receive_json()
        assert response == {"type": "text", "token": "An unverified community report &lt;source&gt;.",
                            "last": True, "interruptible": True, "preemptible": True}
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

    async def handle(message, *args):
        if message == "first report":
            started.set()
            assert await asyncio.to_thread(release.wait, 3)
        completed.append(message)
        return {"answer": message + " answer"}

    monkeypatch.setattr(voice, "utcnow", clock)
    monkeypatch.setattr(voice, "handle_turn", handle)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        ws.send_json(setup())
        ws.send_json(prompt("first report"))
        assert started.wait(3)
        ws.send_json({"type": "interrupt", "utteranceUntilInterrupt": "part of an answer"})
        ws.send_json(prompt("second question"))
        assert second_received.wait(3)
        release.set()
        assert ws.receive_json()["token"] == "second question answer"
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
        ws.send_json(setup())
        ws.send_json(prompt("The Alero clinic pump is broken."))
        assert started.wait(3)
        ws.send({"type": "websocket.disconnect", "code": 1000})
        release.set()
        assert completed.wait(3)


def test_core_error_gives_spoken_failure_and_call_can_continue(client, monkeypatch):
    handler = AsyncMock(side_effect=[RuntimeError("private internal error"), {"answer": "Next answer"}])
    monkeypatch.setattr(voice, "handle_turn", handler)
    with client.websocket_connect("/twilio/ws", headers=signature(BASE + "/twilio/ws")) as ws:
        ws.send_json(setup())
        ws.send_json(prompt("report"))
        response = ws.receive_json()
        assert "may already be saved" in response["token"]
        assert "private" not in response["token"]
        ws.send_json(prompt("question"))
        assert ws.receive_json()["token"] == "Next answer"
        ws.send_json({"type": "error", "description": "provider error"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
