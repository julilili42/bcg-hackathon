"""Twilio webhooks -> brain -> TwiML.  Voice: greeting, speech in (sw-KE or en-US), reply as audio.  SMS: text in, text out.
Also: the JSON feed and the web app (React, built into web/dist)."""
import os, html, json, hmac, hashlib, base64, mimetypes
import azure.functions as func
from gateway import db, brain, tts, phone

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")
STT = {"sw": "sw-KE", "en": "en-US"}  # Google chirp_3 has sw-KE, no sw-TZ; same language on the phone
STT_MODEL = "googlev2_chirp_3"  # the only Twilio speech model with Swahili


def twiml(inner):
    return func.HttpResponse(f"<Response>{inner}</Response>", mimetype="text/xml")


def say(req, text, lang):
    """Local MMS voice when models are present, Twilio's own voice otherwise (English only sounds right there)."""
    name = tts.speak(text, lang)
    if name:
        base = req.url.split("/api/")[0]
        return f"<Play>{base}/api/audio/{name}</Play>"
    return f"<Say language='{STT[lang]}'>{html.escape(text)}</Say>"


def gather(req, prompt, lang):
    return (f"<Gather input='speech dtmf' numDigits='1' language='{STT[lang]}' speechModel='{STT_MODEL}' speechTimeout='auto' "
            f"action='/api/voice/handle?lang={lang}' method='POST'>{say(req, prompt, lang)}</Gather>")


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
    return twiml(gather(req, brain.T["sw"]["greet"], "sw"))


@app.route("voice/handle", methods=["POST"])
def voice_handle(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    lang, f = req.params.get("lang", "sw"), req.form
    if f.get("Digits") == "2":
        return twiml(gather(req, brain.T["en"]["greet"], "en"))
    text = f.get("SpeechResult", "")
    answer, lang = brain.reply(text, lang)
    db.log("voice", f.get("From", "?"), lang, text, answer)
    return twiml(say(req, answer, lang) + "<Hangup/>")


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
