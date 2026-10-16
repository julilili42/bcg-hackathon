"""The virtual demo phone talks to unsigned twins of the Twilio webhooks."""

from fastapi.testclient import TestClient

from reach.settings import reset_settings
from reach.storage.repository import Repository


def _action(xml: str) -> str:
    return xml.split('action="')[1].split('"')[0].replace("&amp;", "&")


def test_sim_call_flow_without_signature_even_when_validation_is_on(
    client: TestClient, seeded: Repository
) -> None:
    client.app.state.settings = client.app.state.settings.model_copy(update={"twilio_validate": True})  # type: ignore[attr-defined]
    assert client.post("/api/voice", data={"From": "+15005550006"}).status_code == 403
    start = client.post("/api/sim/voice", data={"From": "+15005550006"})
    assert start.status_code == 200 and 'language="sw-TZ"' in start.text
    handle = _action(start.text)
    assert handle.startswith("/api/sim/voice/handle?")
    reply = client.post(
        handle, data={"From": "+15005550006", "SpeechResult": "the market is broken", "Digits": ""}
    )
    assert "Unamaanisha Kisarawe Market Tap" in reply.text  # the call starts in Swahili
    answer = _action(reply.text)
    assert answer.startswith("/api/sim/voice/answer?")
    done = client.post(answer, data={"From": "+15005550006", "Digits": "1", "SpeechResult": ""})
    assert "imeandikwa kama imeharibika" in done.text and "<Hangup/>" in done.text
    assert seeded.get_entity("t:market-tap").current_status == "broken"  # type: ignore[union-attr]
    reset_settings()


def test_sim_sms_and_default_sender(client: TestClient) -> None:
    r = client.post("/api/sim/sms", data={"Body": "Is Shule working?"})
    assert r.status_code == 200 and "<Message>" in r.text and "Shule is" in r.text
    assert client.get("/api/health").json()["demo_phone"] is True


def test_sim_is_not_rate_limited_but_can_be_disabled(client: TestClient) -> None:
    for _ in range(8):
        assert "too many" not in client.post("/api/sim/sms", data={"Body": "Is Shule working?"}).text
    client.app.state.settings = client.app.state.settings.model_copy(update={"demo_phone": False})  # type: ignore[attr-defined]
    assert client.post("/api/sim/sms", data={"Body": "hi"}).status_code == 404
    assert client.post("/api/sim/voice", data={}).status_code == 404
    assert client.get("/api/health").json()["demo_phone"] is False
    reset_settings()
