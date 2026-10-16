"""Twilio webhooks -> brain -> TwiML.
Voice: language once per caller (1 sw / 2 en / 3 de, remembered by number) -> one free sentence -> retry if nothing
understood, confirm if the recognition was unsure -> answer -> "press 1 for another". SMS: text in, text out.
Also: the JSON feed and the web app (React, built into web/dist)."""
import os, html, json, hmac, hashlib, base64, mimetypes, urllib.parse
import azure.functions as func
from gateway import db, brain, tts, phone

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")
STT = {"sw": "sw-KE", "en": "en-US", "de": "de-DE"}  # Google chirp_3 has sw-KE, no sw-TZ; same language on the phone
STT_MODEL = "googlev2_chirp_3"  # the only Twilio speech model with Swahili
DIGIT_LANG = {"1": "sw", "2": "en", "3": "de"}
CONFIDENT = 0.6  # below this Twilio confidence we ask "did you say X?"


def twiml(inner):
    return func.HttpResponse(f"<Response>{inner}</Response>", mimetype="text/xml")


def say(req, text, lang):
    """Local MMS voice when models are present, Twilio's own voice otherwise (English only sounds right there)."""
    name = tts.speak(text, lang)
    if name:
        base = req.url.split("/api/")[0]
        return f"<Play>{base}/api/audio/{name}</Play>"
    return f"<Say language='{STT[lang]}'>{html.escape(text)}</Say>"


def gather(req, prompt, lang, attempt=1):
    """Listen for one sentence (or a digit) after the prompt."""
    return (f"<Gather input='speech dtmf' numDigits='1' language='{STT[lang]}' speechModel='{STT_MODEL}' speechTimeout='auto' "
            f"action='/api/voice/handle?lang={lang}&amp;n={attempt}' method='POST'>{say(req, prompt, lang)}</Gather>"
            + say(req, brain.T[lang]["unknown"], lang) + "<Hangup/>")  # reached only if the caller says nothing


def digits(req, prompt_twiml, action, timeout=4):
    """Wait for one key press after the prompt; falls through to whatever follows if none."""
    return f"<Gather input='dtmf' numDigits='1' timeout='{timeout}' action='{action}' method='POST'>{prompt_twiml}</Gather>"


def language_menu(req):
    return digits(req, "".join(say(req, text, lang) for lang, text in brain.MENU), "/api/voice/lang") + language_menu_again()


def language_menu_again():
    return "<Redirect method='POST'>/api/voice</Redirect>"


def finish(req, u, lang, sender):
    """Update + answer, then offer another report; hang up if no key is pressed."""
    answer, lang = brain.answer(u, lang)
    db.log("voice", sender, lang, u.get("text", ""), answer)
    return twiml(say(req, answer, lang)
                 + digits(req, say(req, brain.T[lang]["another"], lang), f"/api/voice/another?lang={lang}")
                 + say(req, brain.T[lang]["bye"], lang) + "<Hangup/>")


def signed(req):
    """Twilio request signature. Only enforced with TWILIO_VALIDATE=1 (off locally so scripts/smoke.sh works)."""
    if os.environ.get("TWILIO_VALIDATE") != "1":
        return True
    payload = req.url + "".join(k + v for k, v in sorted(req.form.items()))
    want = base64.b64encode(hmac.new(os.environ["TWILIO_AUTH_TOKEN"].encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(want, req.headers.get("X-Twilio-Signature", ""))


@app.route("voice", methods=["POST"])
def voice(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    lang = db.get_lang(req.form.get("From", "?"))
    if lang in STT:  # known caller: straight to the question
        return twiml(gather(req, brain.T[lang]["greet"], lang))
    return twiml(language_menu(req))


@app.route("voice/lang", methods=["POST"])
def voice_lang(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    lang = DIGIT_LANG.get(req.form.get("Digits", ""))
    if not lang:
        return twiml(language_menu(req))
    db.set_lang(req.form.get("From", "?"), lang)
    return twiml(gather(req, brain.T[lang]["greet"], lang))


@app.route("voice/handle", methods=["POST"])
def voice_handle(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    f = req.form
    lang, attempt, sender = req.params.get("lang", "sw"), int(req.params.get("n", "1")), f.get("From", "?")
    if f.get("Digits") in DIGIT_LANG:  # a key during the question switches language, also for next time
        lang = DIGIT_LANG[f["Digits"]]
        db.set_lang(sender, lang)
        return twiml(gather(req, brain.T[lang]["greet"], lang))
    text = f.get("SpeechResult", "").strip()
    confidence = float(f.get("Confidence") or 1.0)
    u = brain.understand(text, lang) if text else {"point": None, "status": None, "lang": lang}
    u["text"] = text
    if not u["point"]:
        if attempt < 2:
            return twiml(gather(req, brain.T[lang]["again"], lang, attempt + 1))
        db.log("voice", sender, lang, text, brain.T[lang]["unknown"])
        return twiml(say(req, brain.T[lang]["unknown"], lang) + "<Hangup/>")
    if confidence < CONFIDENT:
        q = urllib.parse.urlencode({"lang": lang, "point": u["point"], "status": u["status"] or "", "text": text})
        return twiml(digits(req, say(req, brain.T[lang]["confirm"].format(p=u["point"]), lang), f"/api/voice/confirm?{q}")
                     + gather(req, brain.T[lang]["again"], lang, 2))
    return finish(req, u, lang, sender)


@app.route("voice/confirm", methods=["POST"])
def voice_confirm(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    lang = req.params.get("lang", "sw")
    if req.form.get("Digits") == "1":
        u = {"point": req.params.get("point"), "status": req.params.get("status") or None, "lang": lang, "text": req.params.get("text", "")}
        return finish(req, u, lang, req.form.get("From", "?"))
    return twiml(gather(req, brain.T[lang]["greet"], lang))


@app.route("voice/another", methods=["POST"])
def voice_another(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    lang = req.params.get("lang", "sw")
    if req.form.get("Digits") == "1":
        return twiml(gather(req, brain.T[lang]["greet"], lang))
    return twiml(say(req, brain.T[lang]["bye"], lang) + "<Hangup/>")


@app.route("sms", methods=["POST"])
def sms(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    f = req.form
    text = f.get("Body", "")
    answer, lang = brain.reply(text)
    db.log("sms", f.get("From", "?"), lang, text, answer)
    return twiml(f"<Message>{html.escape(answer)}</Message>")


@app.route("audio/{name}", methods=["GET"])
def audio(req):
    path = os.path.join(tts.AUDIO, os.path.basename(req.route_params["name"]))
    return func.HttpResponse(open(path, "rb").read(), mimetype="audio/wav") if os.path.exists(path) else func.HttpResponse(status_code=404)


@app.route("events", methods=["GET"])
def events(req):
    return func.HttpResponse(json.dumps({"events": db.events(), "waterpoints": db.waterpoints()}), mimetype="application/json")


@app.route("phone/token", methods=["GET"])
def phone_token(req):
    if not os.environ.get("TWILIO_API_KEY"):
        return func.HttpResponse("Browser phone not set up: run `uv run scripts/phone_setup.py`", status_code=503)
    identity = req.params.get("identity", "demo")[:32]
    return func.HttpResponse(json.dumps({"token": phone.access_token(identity), "number": os.environ.get("TWILIO_NUMBER", "")}),
                             mimetype="application/json")


# --- web app: one React build (web/dist), the page is picked from the URL's last segment (web/src/main.tsx)
@app.route("phone", methods=["GET"])
def phone_page(req):
    return _index()


@app.route("dashboard", methods=["GET"])
def dashboard(req):
    return _index()


@app.route("map", methods=["GET"])
def map_(req):
    return _index()


@app.route("static/{*path}", methods=["GET"])
def static(req):
    path = os.path.normpath(os.path.join(DIST, req.route_params["path"]))
    if not path.startswith(DIST + os.sep) or not os.path.isfile(path):
        return func.HttpResponse(status_code=404)
    return func.HttpResponse(open(path, "rb").read(), mimetype=mimetypes.guess_type(path)[0] or "application/octet-stream")


def _index():
    try:
        return func.HttpResponse(open(os.path.join(DIST, "index.html"), encoding="utf-8").read(), mimetype="text/html")
    except FileNotFoundError:
        return func.HttpResponse("web app not built: cd web && npm install && npm run build", status_code=503)
