from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from reach.channels.twilio_auth import compute_signature
from reach.settings import reset_settings
from reach.storage.repository import Repository
from tests.conftest import load_fixture


def test_voice_start_gathers_in_swahili(client: TestClient) -> None:
    r = client.post("/api/voice", data=load_fixture("voice_empty"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    assert '<Gather input="speech dtmf"' in r.text and 'language="sw-TZ"' in r.text
    assert "Karibu Reach" in r.text and 'hints="' in r.text


def test_call_can_start_in_english(client: TestClient) -> None:
    r = client.post("/api/voice?lang=en", data=load_fixture("voice_empty"))
    assert 'language="en-US"' in r.text and "Welcome to Reach" in r.text and "lang=en" in r.text
    sim = client.post("/api/sim/voice?lang=en", data={})
    assert 'language="en-US"' in sim.text and "/api/sim/voice/handle?lang=en" in sim.text.replace(
        "&amp;", "&"
    )


def test_press_two_switches_to_english(client: TestClient) -> None:
    r = client.post(
        "/api/voice/handle?lang=sw&domain=water", data={**load_fixture("voice_empty"), "Digits": "2"}
    )
    assert 'language="en-US"' in r.text and "Welcome to Reach" in r.text


def test_voice_report_records_and_hangs_up(client: TestClient, seeded: Repository) -> None:
    r = client.post("/api/voice/handle?lang=sw&domain=water", data=load_fixture("voice_report_sw"))
    assert "<Say>" in r.text and "imeandikwa kama imeharibika" in r.text and "<Hangup/>" in r.text
    assert seeded.get_entity("t:shule").current_status == "broken"  # type: ignore[union-attr]
    assert seeded.list_interactions()[0].channel == "voice"


def test_voice_empty_speech_retries_once_then_says_goodbye(client: TestClient) -> None:
    first = client.post("/api/voice/handle?lang=en&domain=water&retry=0", data=load_fixture("voice_empty"))
    assert "<Gather" in first.text and "did not hear" in first.text and "retry=1" in first.text
    second = client.post("/api/voice/handle?lang=en&domain=water&retry=1", data=load_fixture("voice_empty"))
    assert "Goodbye" in second.text and "<Hangup/>" in second.text


def _action(twiml: str) -> str:
    return twiml.split('action="')[1].split('"')[0].replace("&amp;", "&")


def test_voice_uncertain_match_asks_then_press_one_records(client: TestClient, seeded: Repository) -> None:
    r = client.post("/api/voice/handle?lang=en&domain=water", data=load_fixture("voice_uncertain_en"))
    assert '<Gather input="speech dtmf"' in r.text and "Did you mean Kisarawe Market Tap? Press one" in r.text
    assert 'hints="Kisarawe Market Tap"' in r.text
    action = _action(r.text)
    assert urlparse(action).path == "/api/voice/answer" and parse_qs(urlparse(action).query)["lang"] == ["en"]
    done = client.post(action, data={**load_fixture("voice_uncertain_en"), "Digits": "1", "SpeechResult": ""})
    assert "recorded as broken" in done.text and "<Hangup/>" in done.text
    assert seeded.get_entity("t:market-tap").current_status == "broken"  # type: ignore[union-attr]


def test_voice_no_then_name_completes_the_report(client: TestClient, seeded: Repository) -> None:
    r = client.post("/api/voice/handle?lang=en&domain=water", data=load_fixture("voice_uncertain_en"))
    action = _action(r.text)
    cancel = client.post(
        action, data={**load_fixture("voice_uncertain_en"), "Digits": "2", "SpeechResult": ""}
    )
    assert "<Gather" in cancel.text and "say the water point name again" in cancel.text
    named = client.post(
        _action(cancel.text), data={**load_fixture("voice_uncertain_en"), "SpeechResult": "Bwawa"}
    )
    assert "Bwawa is recorded as broken" in named.text and "<Hangup/>" in named.text


def test_voice_status_without_place_asks_which_point(client: TestClient, seeded: Repository) -> None:
    form = {**load_fixture("voice_uncertain_en"), "SpeechResult": "it is broken"}
    r = client.post("/api/voice/handle?lang=en&domain=water", data=form)
    assert "You said broken. Which water point?" in r.text and "<Gather" in r.text and 'hints="' in r.text
    done = client.post(_action(r.text), data={**form, "SpeechResult": "Shule"})
    assert "Shule is recorded as broken" in done.text
    assert seeded.get_entity("t:shule").current_status == "broken"  # type: ignore[union-attr]


def test_voice_answer_without_input_retries_then_says_goodbye(client: TestClient) -> None:
    form = {**load_fixture("voice_empty"), "SpeechResult": ""}
    first = client.post("/api/voice/answer?lang=en&domain=water", data=form)
    assert "<Gather" in first.text and "retry=1" in first.text
    second = client.post("/api/voice/answer?lang=en&domain=water&retry=1", data=form)
    assert "Goodbye" in second.text and "<Hangup/>" in second.text


def test_sms_report_query_help(client: TestClient) -> None:
    r = client.post("/api/sms", data=load_fixture("sms_report_sw"))
    assert "<Message>" in r.text and "Shule imeandikwa kama imeharibika" in r.text and "dakika" in r.text
    q = client.post("/api/sms", data=load_fixture("sms_query_en"))
    assert "Soko is broken." in q.text and "minutes on foot" in q.text
    h = client.post("/api/sms", data=load_fixture("sms_help"))
    assert "Send the water point name" in h.text
    empty = client.post("/api/sms", data={**load_fixture("sms_help"), "Body": ""})
    assert "Send the water point name" in empty.text


def test_sms_health_domain(client: TestClient, seeded: Repository) -> None:
    r = client.post("/api/sms", data=load_fixture("sms_health_sw"))
    assert "Msanga Dispensary imeandikwa kama imefungwa" in r.text
    assert seeded.get_entity("t:msanga").current_status == "closed"  # type: ignore[union-attr]


def test_sms_rate_limit(client: TestClient) -> None:
    for _ in range(5):
        assert "too many" not in client.post("/api/sms", data=load_fixture("sms_query_en")).text
    assert "too many messages" in client.post("/api/sms", data=load_fixture("sms_query_en")).text


def test_signature_validation(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client.app.state.settings = client.app.state.settings.model_copy(update={"twilio_validate": True})  # type: ignore[attr-defined]
    form = load_fixture("sms_query_en")
    assert client.post("/api/sms", data=form).status_code == 403
    good = compute_signature("test-token", "http://testserver/api/sms", form)
    ok = client.post("/api/sms", data=form, headers={"X-Twilio-Signature": good})
    assert ok.status_code == 200 and "Soko" in ok.text
    behind_proxy = compute_signature("test-token", "https://demo.example.org/api/sms", form)
    proxied = client.post(
        "/api/sms",
        data=form,
        headers={
            "X-Twilio-Signature": behind_proxy,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "demo.example.org",
        },
    )
    assert proxied.status_code == 200
    reset_settings()


def test_audio_404_for_unknown_or_traversal(client: TestClient) -> None:
    assert client.get("/api/audio/nope.wav").status_code == 404
    assert client.get("/api/audio/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_sms_follow_up_conversation(client: TestClient, seeded: Repository) -> None:
    base = load_fixture("sms_help")
    ask = client.post("/api/sms", data={**base, "Body": "hakuna maji"})
    assert "Kisima gani?" in ask.text
    done = client.post("/api/sms", data={**base, "Body": "Soko"})
    assert "Soko imeandikwa kama haina maji" in done.text
    assert seeded.get_entity("t:soko").current_status == "empty"  # type: ignore[union-attr]
