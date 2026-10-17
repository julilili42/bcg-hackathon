"""Outbound console contract: all provider calls are mocked; tests never dial."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

import infrastructure as db
from scripts import demo_call as console


@pytest.fixture
def configured(monkeypatch):
    values = dict(TWILIO_ACCOUNT_SID="AC" + "1" * 32, TWILIO_AUTH_TOKEN="synthetic-token",
        PUBLIC_BASE_URL="https://waterline.example", TWILIO_PHONE_NUMBER="+15555550100",
        DEMO_CALLEE_NUMBER="+15555550123", DEMO_ALLOWED_NUMBERS="+15555550123")
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in ("DEMO_OPENING_PIPE_ID", "DEMO_OPENING_MESSAGE", "TWILIO_RELAY_TTS_PROVIDER", "TWILIO_RELAY_VOICE"):
        monkeypatch.delenv(key, raising=False)
    return console.settings()


def test_c_dials_once_and_masks_recipient(configured):
    client = Mock()
    client.calls.list.return_value = []
    client.calls.create.return_value = SimpleNamespace(sid="CA" + "2" * 32, status="queued")
    keys = iter("ccq")
    output = []
    console.run_console(client, configured, key_reader=lambda: next(keys), clock=lambda: 0, output=output.append)
    client.calls.create.assert_called_once()
    request = client.calls.create.call_args.kwargs
    assert request["to"] == configured[-1] and request["from_"] == configured[-2]
    assert request["record"] is False
    relay = ET.fromstring(request["twiml"]).find("Connect/ConversationRelay")
    assert "AI" in relay.attrib["welcomeGreeting"]
    assert relay.attrib["transcriptionProvider"] == "Deepgram"
    assert relay.attrib["ttsProvider"] == "Google"
    assert relay.attrib["url"] == "wss://waterline.example/twilio/ws"
    assert any(p.attrib == {"name": "waterline_mode", "value": "outbound"} for p in relay)
    logs = "\n".join(output)
    assert "CA" + "2" * 32 in logs and "queued" in logs and "blocked" in logs
    assert configured[-1] not in logs and "synthetic-token" not in logs


@pytest.mark.parametrize("key,value", [("TWILIO_AUTH_TOKEN", ""), ("DEMO_CALLEE_NUMBER", "123"),
    ("DEMO_ALLOWED_NUMBERS", ""), ("DEMO_ALLOWED_NUMBERS", "+15555550999"),
    ("PUBLIC_BASE_URL", "http://waterline.example")])
def test_bad_configuration_never_dials(configured, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    client = Mock()
    keys = iter("cq")
    console.run_console(client, configured, key_reader=lambda: next(keys), clock=lambda: 0, output=lambda _: None)
    client.calls.create.assert_not_called()


def test_contextual_opening_reads_registry_without_writing(configured, monkeypatch):
    identifier = "ff50877c-99aa-5dbb-a163-0a1d6b643a50"
    monkeypatch.setenv("DATABASE_URL", "configured-by-fixture")
    monkeypatch.setenv("DEMO_OPENING_PIPE_ID", identifier)
    lookup = Mock(return_value=dict(name="Alero school borehole", village="Alero", status="broken",
        status_observed_at=datetime(2026, 10, 17, tzinfo=timezone.utc)))
    monkeypatch.setattr(db, "get_pipe_by_id", lookup)
    monkeypatch.setattr(db, "get_pipes", lambda *args: [])
    opening, pipe_id = console.prepare_opening()
    assert pipe_id == identifier and identifier not in opening
    assert "AI" in opening and "broken" in opening and "unverified" in opening
    assert not any(char.isdigit() for char in opening)
    lookup.assert_called_once_with(identifier)


def test_opening_suggests_latest_working_asset_from_database(configured, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "configured-by-fixture")
    monkeypatch.setenv("DEMO_OPENING_PIPE_ID", "school-id")
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(db, "get_pipe_by_id", lambda _: dict(name="School pump", village="Alero",
        status="broken", status_observed_at=now))
    candidates = [dict(id="clinic-id", name="Clinic pump", status_observed_at=now)]
    monkeypatch.setattr(db, "get_pipes", lambda village, status: candidates)
    assert "Clinic pump is reported working" in console.prepare_opening()[0]
    candidates[:] = [dict(id="market-id", name="Market tap", status_observed_at=now)]
    assert "Market tap is reported working" in console.prepare_opening()[0]
    candidates.clear()
    opening = console.prepare_opening()[0]
    assert "Clinic pump" not in opening and "another dated working report" in opening


def test_no_answer_is_reported_without_redial(configured):
    client = Mock()
    client.calls.list.return_value = []
    client.calls.create.return_value = SimpleNamespace(sid="CA" + "2" * 32, status="queued")
    client.calls.return_value.fetch.return_value.status = "no-answer"
    keys = iter(["c", "", "q"])
    ticks = iter([0, 3, 3, 4])
    output = []
    console.run_console(client, configured, key_reader=lambda: next(keys), clock=lambda: next(ticks), output=output.append)
    client.calls.create.assert_called_once()
    assert "[CALL] Status: no-answer" in output
    assert not any("conversation active" in line.lower() for line in output)


def test_existing_call_is_monitored_without_new_dial(configured):
    client = Mock()
    client.calls.list.return_value = [SimpleNamespace(sid="CA" + "3" * 32, status="in-progress")]
    client.calls.return_value.fetch.return_value.status = "in-progress"
    keys = iter("ccq")
    console.run_console(client, configured, key_reader=lambda: next(keys), clock=lambda: 0, output=lambda _: None)
    client.calls.create.assert_not_called()


def test_uncertain_dial_result_blocks_retry_and_redacts_errors(configured):
    client = Mock()
    client.calls.list.return_value = []
    client.calls.create.side_effect = TimeoutError("private error containing " + configured[-1])
    keys = iter("ccq")
    output = []
    console.run_console(client, configured, key_reader=lambda: next(keys), clock=lambda: 0, output=output.append)
    client.calls.create.assert_called_once()
    assert configured[-1] not in "\n".join(output)
    assert any("blocked" in line for line in output)


def test_elevenlabs_requires_an_explicit_voice(configured, monkeypatch):
    monkeypatch.setenv("TWILIO_RELAY_TTS_PROVIDER", "ElevenLabs")
    with pytest.raises(ValueError, match="TWILIO_RELAY_VOICE"):
        console.outbound_twiml(configured[2], "WaterLine AI here.")
    monkeypatch.setenv("TWILIO_RELAY_VOICE", "demo-voice-id")
    relay = ET.fromstring(console.outbound_twiml(configured[2], "WaterLine AI here.")).find("Connect/ConversationRelay")
    assert relay.attrib["ttsProvider"] == "ElevenLabs" and relay.attrib["voice"] == "demo-voice-id"
