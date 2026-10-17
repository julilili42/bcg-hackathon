"""Optional headless Chrome tests: RUN_BROWSER_SMOKE=1 python -m pytest tests/test_browser_demo.py."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB = Path(__file__).resolve().parents[1] / "web"


def test_voice_demo_served_without_voice_credentials(monkeypatch):
    import app as api
    monkeypatch.setattr(api, "initialize", lambda: None)
    with TestClient(api.app) as client:
        page = client.get("/demo")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "Start conversation" in page.text
        script = client.get("/demo-assets/voice.js")
        assert script.status_code == 200
        assert client.get("/demo-assets/../../.env").status_code == 404


@pytest.fixture
def browser_page():
    if os.getenv("RUN_BROWSER_SMOKE") != "1":
        pytest.skip("set RUN_BROWSER_SMOKE=1 and install playwright for headless Chrome checks")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://waterline.test/demo", lambda route: route.fulfill(
            body=(WEB / "voice.html").read_text(), content_type="text/html"))
        page.route("https://waterline.test/demo-assets/voice.js", lambda route: route.fulfill(
            body=(WEB / "voice.js").read_text(), content_type="text/javascript"))
        page.add_init_script("""
            class MockRecognition {
                constructor() { window.recognition = this; }
                start() { this.started = true; }
                stop() { this.onend(); }
                abort() {}
            }
            window.SpeechRecognition = MockRecognition;
            window.spoken = [];
            window.Audio = class {
                constructor(src) { this.src = src; window.playback = this; }
                async play() { window.spoken.push(this.src); }
                pause() { this.paused = true; }
                removeAttribute() {}
                load() {}
            };
            window.emitSpeech = (text, final) => {
                const result = [{transcript: text}]; result.isFinal = final;
                window.recognition.onresult({results: [result]});
            };
        """)
        page.route("**/speech", lambda route: route.fulfill(body=b"RIFF-test-audio", content_type="audio/wav"))
        yield page
        browser.close()


def start_without_spoken_greeting(page):
    # These tests isolate turns after the opener; the greeting has its own playback test.
    page.locator("#read-aloud").evaluate("el => el.checked = false")
    page.locator("#talk").click()
    page.locator("#read-aloud").evaluate("el => el.checked = true")


def test_greeting_plays_before_microphone_starts(browser_page):
    page = browser_page
    requests = []
    def speech(route):
        requests.append(route.request.post_data_json)
        route.fulfill(body=b"RIFF-test-audio", content_type="audio/wav")
    page.route("**/speech", speech)
    page.goto("https://waterline.test/demo")
    page.locator("#talk").click()
    page.wait_for_function("window.spoken.length === 1")
    assert requests[0]["text"] == "Hey WaterLine here, how can i help you?"
    assert not page.evaluate("Boolean(recognition.started)")
    page.evaluate("window.playback.onended()")
    page.wait_for_function("recognition.started === true")
    assert page.locator("body").get_attribute("data-mode") == "listening"


def answer(route):
    route.fulfill(json={"intent": "report", "answer": "I recorded your report as unverified community information.",
                        "reports": [], "sources": [], "turn_id": "demo-turn"})


def test_only_final_transcript_submitted_and_mic_off_during_reply(browser_page):
    page = browser_page
    requests = []
    def respond(route):
        requests.append(route.request.post_data_json)
        answer(route)
    page.route("**/interact", respond)
    page.goto("https://waterline.test/demo")
    page.locator(".settings").evaluate("el => el.open = true")
    page.locator("#auto-send").check()
    start_without_spoken_greeting(page)
    page.evaluate("emitSpeech('The Alero school', false)")
    assert page.locator("#transcript").input_value() == ""
    assert requests == []
    text = "The Alero school borehole is broken today."
    page.evaluate("text => emitSpeech(text, true)", text)
    page.evaluate("recognition.onend()")
    page.wait_for_function("window.spoken.length === 1")
    assert len(requests) == 1 and requests[0]["message"] == text
    assert page.locator("#talk").is_disabled()
    page.evaluate("() => { window.previousPlaybackError = window.playback.onerror; }")
    page.locator("#quiet").click()
    page.wait_for_function("document.body.dataset.mode === 'listening'")
    page.evaluate("window.previousPlaybackError()")  # A cancelled reply cannot interrupt the next recording.
    assert page.locator("body").get_attribute("data-mode") == "listening"
    assert page.locator("#conversation .message:has(details)").count() == 1


def test_retry_reuses_turn_id(browser_page):
    page = browser_page
    requests = []
    def respond(route):
        requests.append(route.request.post_data_json)
        if len(requests) == 1:
            route.abort()
        else:
            answer(route)
    page.route("**/interact", respond)
    page.goto("https://waterline.test/demo")
    page.locator(".settings").evaluate("el => el.open = true")
    page.locator("#keyboard").click()
    page.locator("#transcript").fill("The Alero market water point is broken.")
    page.locator("#send").click()
    page.get_by_role("status").filter(has_text="Could not get an answer").wait_for()
    page.locator("#send").click()
    page.wait_for_function("window.spoken.length === 1")
    assert len(requests) == 2 and requests[0] == requests[1]


def test_recognition_error_never_submits_partial_speech(browser_page):
    page = browser_page
    requests = []
    page.route("**/interact", lambda route: requests.append(route.request.post_data_json) or answer(route))
    page.goto("https://waterline.test/demo")
    page.locator(".settings").evaluate("el => el.open = true")
    page.locator("#auto-send").check()
    start_without_spoken_greeting(page)
    page.evaluate("emitSpeech('Alero broken', false); recognition.onerror({error: 'not-allowed'}); recognition.onend()")
    assert requests == []
    assert "denied" in page.locator("#status").inner_text()
    assert page.locator("#talk").is_enabled()


def test_typed_fallback_and_untrusted_text_rendered_safely(browser_page):
    page = browser_page
    page.add_init_script("window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;")
    malicious = '<img src=x onerror="window.injected=true">'
    page.route("**/interact", lambda route: route.fulfill(json={"intent": "query", "answer": malicious,
        "reports": [], "sources": [{"text": malicious}], "turn_id": "demo"}))
    page.goto("https://waterline.test/demo")
    page.locator(".settings").evaluate("el => el.open = true")
    assert page.locator("#talk").is_disabled()
    page.locator("#transcript").fill("Is the school borehole working?")
    page.locator("#send").click()
    page.wait_for_function("window.spoken.length === 1")
    assert page.locator("#conversation img").count() == 0
    assert page.evaluate("window.injected === undefined")
    assert malicious in page.locator("#conversation").inner_text()


def test_spoken_reply_finishes_then_hands_free_listening_resumes(browser_page):
    page = browser_page
    page.route("**/interact", answer)
    page.goto("https://waterline.test/demo")
    start_without_spoken_greeting(page)
    assert page.locator("body").get_attribute("data-mode") == "listening"
    page.evaluate("emitSpeech('Is the Alero school borehole working?', true); recognition.onend()")
    page.wait_for_function("window.spoken.length === 1")
    assert page.locator("body").get_attribute("data-mode") == "speaking"
    assert page.locator("#talk").is_disabled()
    page.evaluate("window.playback.onended()")
    page.wait_for_function("document.body.dataset.mode === 'listening'")
    page.locator("#end-session").click()
    assert page.locator("body").get_attribute("data-mode") == "idle"
    assert page.locator("#talk").is_enabled()
    # Late recognition results after ending a session must not create another turn.
    page.evaluate("emitSpeech('The pump is broken', true); recognition.onend()")
    assert page.locator("#transcript").input_value() == ""
    assert page.locator("#conversation .resident").count() == 1


def test_end_during_thinking_prevents_playback_and_replay_still_works(browser_page):
    page = browser_page
    held = []
    page.route("**/interact", lambda route: held.append(route))
    page.goto("https://waterline.test/demo")
    start_without_spoken_greeting(page)
    page.evaluate("emitSpeech('The Alero school borehole is broken.', true); recognition.onend()")
    page.wait_for_function("document.body.dataset.mode === 'thinking'")
    page.locator("#end-session").click()
    assert held
    answer(held[0])
    page.locator("#conversation .message:has(details)").wait_for()
    assert page.evaluate("window.spoken.length") == 0
    page.locator("#replay").click()
    page.wait_for_function("window.spoken.length === 1")
    assert page.locator("body").get_attribute("data-mode") == "speaking"


def test_neural_voice_selection_and_replay_cache(browser_page):
    page = browser_page
    speech_requests = []
    def speech(route):
        speech_requests.append(route.request.post_data_json)
        route.fulfill(body=b"RIFF-test-audio", content_type="audio/wav")
    page.route("**/speech", speech)
    page.route("**/interact", answer)
    page.goto("https://waterline.test/demo")
    page.locator("#keyboard").click()
    page.locator("#transcript").fill("Is the school borehole working?")
    page.locator("#send").click()
    page.wait_for_function("window.spoken.length === 1")
    assert speech_requests[0]["voice"] == "en-US-AvaMultilingualNeural"
    page.evaluate("window.playback.onended()")
    page.locator("#replay").click()
    page.wait_for_function("window.spoken.length === 2")
    assert len(speech_requests) == 1
    page.evaluate("window.playback.onended()")
    page.locator(".settings").evaluate("el => el.open = true")
    page.locator("#voice").select_option("en-US-AndrewMultilingualNeural")
    page.locator("#replay").click()
    page.wait_for_function("window.spoken.length === 3")
    assert speech_requests[-1]["voice"] == "en-US-AndrewMultilingualNeural"


def test_cancel_pending_speech_never_plays_late_audio(browser_page):
    page = browser_page
    held = []
    page.route("**/interact", answer)
    page.route("**/speech", lambda route: held.append(route))
    page.goto("https://waterline.test/demo")
    start_without_spoken_greeting(page)
    page.evaluate("emitSpeech('Is the Alero school borehole working?', true); recognition.onend()")
    page.get_by_role("status").filter(has_text="Preparing your spoken reply").wait_for()
    assert held
    page.locator("#end-session").click()
    held[0].fulfill(body=b"RIFF-test-audio", content_type="audio/wav")
    assert page.evaluate("window.spoken.length") == 0
    assert page.locator("body").get_attribute("data-mode") == "idle"


def test_missing_speech_setup_preserves_answer_without_reposting_report(browser_page):
    page = browser_page
    page.route("**/interact", answer)
    page.route("**/speech", lambda route: route.fulfill(status=503, json={"detail": "Spoken replies are not configured yet. Your text answer is still available."}))
    page.goto("https://waterline.test/demo")
    start_without_spoken_greeting(page)
    page.evaluate("emitSpeech('The Alero school borehole is broken.', true); recognition.onend()")
    page.get_by_role("status").filter(has_text="not configured yet").wait_for()
    assert page.locator("#conversation .message:has(details)").count() == 1
    assert page.locator("body").get_attribute("data-mode") == "error"
    assert page.evaluate("window.spoken.length") == 0
