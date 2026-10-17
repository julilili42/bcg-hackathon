"""Azure speech contract, credential isolation, and recoverable provider errors."""
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app as api
import speech


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "initialize", lambda: None)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-speech-key")
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", speech.DEFAULT_ENDPOINT)
    with TestClient(api.app) as client:
        yield client


def upstream(monkeypatch, status=200):
    response = httpx.Response(status, content=b"ID3synthetic-audio" if status == 200 else b"private upstream error",
        headers={"content-type": "audio/mpeg"}, request=httpx.Request("POST", "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"))
    remote = Mock()
    remote.post = AsyncMock(return_value=response)
    context = Mock()
    context.__aenter__ = AsyncMock(return_value=remote)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(speech.httpx, "AsyncClient", Mock(return_value=context))
    return remote


def test_azure_ava_voice_and_secret_stay_on_server(client, monkeypatch):
    remote = upstream(monkeypatch)
    response = client.post("/speech", json={"text": "The pump was reported broken today. This is unverified."})
    assert response.status_code == 200 and response.content == b"ID3synthetic-audio"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    request = remote.post.call_args.kwargs
    assert remote.post.call_args.args[0] == "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request["headers"]["Ocp-Apim-Subscription-Key"] == "synthetic-speech-key"
    assert request["headers"]["Content-Type"] == "application/ssml+xml"
    assert request["headers"]["X-Microsoft-OutputFormat"] == "audio-24khz-96kbitrate-mono-mp3"
    from xml.etree import ElementTree as ET
    root = ET.fromstring(request["content"])
    voice = root.find("{http://www.w3.org/2001/10/synthesis}voice")
    assert voice.attrib["name"] == "en-US-AvaMultilingualNeural"
    assert "".join(root.itertext()) == "The pump was reported broken today. This is unverified."
    assert "synthetic-speech-key" not in response.text


def test_missing_key_keeps_agent_text_available(client, monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "unused-previous-provider-key")
    response = client.post("/speech", json={"text": "An answer."})
    assert response.status_code == 503 and "AZURE_SPEECH_KEY" in response.json()["detail"]
    monkeypatch.setattr(api, "handle_turn", AsyncMock(return_value={"answer": "Text still works."}))
    assert client.post("/interact", json={"message": "Working?"}).json()["answer"] == "Text still works."


def test_internal_references_are_not_synthesized(client, monkeypatch):
    remote = upstream(monkeypatch)
    identifier = "b18bb8b5-e4e9-5bb2-a8d4-0755e6afef6f"
    response = client.post("/speech", json={"text": f"A **community report {identifier}** says the clinic pump is broken."})
    assert response.status_code == 200
    ssml = remote.post.call_args.kwargs["content"].decode()
    assert identifier not in ssml and "**" not in ssml
    assert "says the clinic pump is broken" in ssml


def test_upstream_failure_does_not_expose_details(client, monkeypatch):
    upstream(monkeypatch, 401)
    response = client.post("/speech", json={"text": "An answer.", "voice": "en-US-AndrewMultilingualNeural"})
    assert response.status_code == 503
    assert "private upstream error" not in response.text and "synthetic-speech-key" not in response.text
    assert "text answer" in response.json()["detail"]


@pytest.mark.parametrize("body", [{"text": " "}, {"text": "x" * 4097},
    {"text": "Hi", "voice": "invented-voice"}, {"text": "Hi", "model": "arbitrary-model"}])
def test_invalid_speech_requests_rejected(client, body):
    assert client.post("/speech", json=body).status_code == 422


def test_quota_error_is_actionable_without_losing_text(client, monkeypatch):
    upstream(monkeypatch, 429)
    response = client.post("/speech", json={"text": "An unverified community report."})
    assert response.status_code == 503
    assert "quota or rate limit reached" in response.json()["detail"]
    assert "Hear last reply" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", [speech.DEFAULT_ENDPOINT,
    "https://germanywestcentral.tts.speech.microsoft.com/",
    "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"])
def test_regional_endpoint_mapping(monkeypatch, endpoint):
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", endpoint)
    assert speech.synthesis_endpoint() == "https://germanywestcentral.tts.speech.microsoft.com/cognitiveservices/v1"


@pytest.mark.parametrize("endpoint", ["http://germanywestcentral.api.cognitive.microsoft.com/",
    "https://example.com/", "https://germanywestcentral.api.cognitive.microsoft.com/?key=anything"])
def test_invalid_endpoint_rejected_before_sending_key(client, monkeypatch, endpoint):
    remote = upstream(monkeypatch)
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", endpoint)
    assert client.post("/speech", json={"text": "An answer."}).status_code == 503
    remote.post.assert_not_called()


def test_answer_cannot_inject_speech_markup(client, monkeypatch):
    from xml.etree import ElementTree as ET
    remote = upstream(monkeypatch)
    text = 'A & B <voice name="other">unverified</voice>'
    response = client.post("/speech", json={"text": text})
    assert response.status_code == 200
    root = ET.fromstring(remote.post.call_args.kwargs["content"])
    assert "".join(root.itertext()) == text
    assert len(root.findall(".//{http://www.w3.org/2001/10/synthesis}voice")) == 1
