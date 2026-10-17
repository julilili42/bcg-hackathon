"""The Gemini voice bridge without Gemini or Twilio: a scripted Live session and a fake media stream. `uv run pytest -q`"""
import asyncio, base64, json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from google.genai import types

from gateway import db, graph as g, knowledge as kb, live

POINTS = [dict(id=1, name="Zahanati", village="Kigero", lat=-6.7788, lon=38.8615, status="ok", updated="2026-10-16 08:00:00"),
          dict(id=2, name="Mama Nasa", village="Vikuge", lat=-6.7700, lon=38.8600, status="ok", updated="2026-10-16 08:00:00")]
VILLAGES = [dict(name="Kigero", lat=-6.7790, lon=38.8610), dict(name="Vikuge", lat=-6.7705, lon=38.8605)]
HAZARDS, LOG = [], []


@pytest.fixture(autouse=True)
def table(monkeypatch):
    points = [dict(p) for p in POINTS]
    HAZARDS.clear(); LOG.clear()
    monkeypatch.setattr(db, "waterpoints", lambda: [dict(p) for p in points])
    monkeypatch.setattr(db, "villages", lambda: [dict(v) for v in VILLAGES])
    monkeypatch.setattr(db, "set_status", lambda wp_id, status: next(p for p in points if p["id"] == wp_id).update(status=status))
    monkeypatch.setattr(db, "add_hazard", lambda *a: HAZARDS.append(a))
    monkeypatch.setattr(db, "log", lambda *a: LOG.append(a))
    monkeypatch.setattr(kb, "store_facts", lambda *a: ["fact-id"])
    monkeypatch.setattr(kb, "hybrid_search", lambda *a: [])
    monkeypatch.setattr(kb, "status_history", lambda *a: [])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TWILIO_VALIDATE", raising=False)
    return points


def test_audio_conversion_keeps_the_duration():
    up, down = live.Resampler(8000, 16000), live.Resampler(24000, 8000)
    twenty_ms = base64.b64encode(b"\xff" * 160).decode()  # mu-law silence, 160 samples at 8 kHz
    pcm16k = b"".join(live.caller_to_gemini(twenty_ms, up) for _ in range(50))
    assert abs(len(pcm16k) - 16000 * 2) <= 8  # one second at 16 kHz, 16 bit
    mulaw = b"".join(base64.b64decode(live.gemini_to_caller(b"\x00\x00" * 480, down)) for _ in range(50))
    assert abs(len(mulaw) - 8000) <= 4  # one second back at 8 kHz, one byte per sample


def test_tools_run_the_brain(table):
    r = live.run_tool("report_water_point", {"water_point": "Zahanati", "status": "broken", "statement": "Zahanati is broken", "language": "en"}, "+255700", "c:1")
    assert r["understood"] and table[0]["status"] == "broken" and r["answer"].startswith("Thank you. Zahanati is recorded as broken.")
    assert LOG[-1] == ("voice", "+255700", "en", "Zahanati is broken", r["answer"], "Kigero", "Zahanati", "status", "broken")
    r = live.run_tool("report_hazard", {"kind": "animals", "village": "Vikuge", "statement": "a snake on the path", "language": "sw"}, "+255700", "c:2")
    assert HAZARDS == [("Vikuge", "Mama Nasa", "animals", "a snake on the path", g.anonymous("+255700"))]
    assert r["identity_protected"] and LOG[-1][1] == g.anonymous("+255700") and "Jina na namba yako havionyeshwi" in r["answer"]
    r = live.run_tool("ask", {"question": "Is Atlantis working?", "water_point": "Atlantis", "kind": "current_status", "language": "en"}, "+255700", "c:3")
    assert not r["understood"]  # Gemini is told to ask for the name again


class Session:
    """A scripted Gemini Live session: each turn is a list of messages; a tool call waits for its response."""
    def __init__(self, turns):
        self.turns, self.audio, self.greeting, self.responses = list(turns), [], [], []
        self.answered = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_realtime_input(self, audio):
        self.audio.append(audio)

    async def send_client_content(self, turns, turn_complete=True):
        self.greeting.append(turns)

    async def send_tool_response(self, function_responses):
        self.responses.append(function_responses)
        self.answered.set()

    async def receive(self):
        if not self.turns:
            await asyncio.Event().wait()  # nothing more to say: like a quiet line
        for m in self.turns.pop(0):
            yield m
            if m.tool_call:
                await self.answered.wait()
                self.answered.clear()


def tool(name, **args):
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[types.FunctionCall(id=name, name=name, args=args)]))


def speech(pcm, done=True):
    return types.LiveServerMessage(server_content=types.LiveServerContent(
        model_turn=types.Content(role="model", parts=[types.Part(inline_data=types.Blob(data=pcm, mime_type="audio/pcm;rate=24000"))]),
        turn_complete=done))


@pytest.mark.asyncio
async def test_a_call_reports_a_hazard_speaks_and_hangs_up(monkeypatch):
    session = Session([
        [tool("report_hazard", kind="harassment", village="Kigero", water_point="Zahanati", statement="men harass women on the path", language="en"),
         speech(b"\x00\x00" * 480)],
        [tool("end_call"), speech(b"\x00\x00" * 480)],
    ])
    monkeypatch.setattr(live, "connect", lambda: session)
    async with TestClient(TestServer(live.app())) as client:
        twiml = await (await client.post("/voice", data={"From": "+255711"})).text()
        assert "/media" in twiml and 'name="from" value="+255711"' in twiml and twiml.startswith("<Response><Connect><Stream url=\"wss://")
        ws = await client.ws_connect("/media")
        await ws.send_str(json.dumps({"event": "connected"}))
        await ws.send_str(json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1", "customParameters": {"from": "+255711"}}}))
        await ws.send_str(json.dumps({"event": "media", "media": {"payload": base64.b64encode(b"\xff" * 160).decode()}}))
        heard = []
        async for msg in ws:
            m = json.loads(msg.data)
            heard.append(m["event"])
            assert m["streamSid"] == "MZ1"
            if m["event"] == "mark":  # Twilio confirms the goodbye was played
                await ws.send_str(json.dumps({"event": "mark", "streamSid": "MZ1", "mark": {"name": "bye"}}))
        assert heard == ["media", "media", "mark"] and ws.closed
    assert session.greeting and session.audio[0].mime_type == "audio/pcm;rate=16000"
    assert HAZARDS == [("Kigero", "Zahanati", "harassment", "men harass women on the path", g.anonymous("+255711"))]
    assert LOG == [("voice", g.anonymous("+255711"), "en", "men harass women on the path", LOG[0][4], "Kigero", "Zahanati", "hazard", "harassment")]
    answer = session.responses[0][0]
    assert answer.id == "report_hazard" and answer.response["identity_protected"] and "not shown" in answer.response["answer"]
