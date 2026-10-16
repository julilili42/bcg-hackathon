"""Twilio webhooks -> brain -> TwiML.  Voice: greeting, speech in (sw-TZ or en-US), reply as audio.  SMS: text in, text out."""
import os, html, json, hmac, hashlib, base64
import azure.functions as func
import db, brain, tts

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
STT = {"sw": "sw-TZ", "en": "en-US"}


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
    return (f"<Gather input='speech dtmf' numDigits='1' language='{STT[lang]}' speechTimeout='auto' "
            f"action='/api/voice/handle?lang={lang}' method='POST'>{say(req, prompt, lang)}</Gather>")


def signed(req):
    """Twilio request signature. Only enforced with TWILIO_VALIDATE=1 (off locally so smoke.sh works)."""
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
    answer = brain.reply(text, lang)
    db.log("voice", f.get("From", "?"), lang, text, answer)
    return twiml(say(req, answer, lang) + "<Hangup/>")


@app.route("sms", methods=["POST"])
def sms(req):
    if not signed(req):
        return func.HttpResponse(status_code=403)
    f = req.form
    text = f.get("Body", "")
    lang = "sw" if any(w in text.lower() for w in ["kisima", "maji", "imeharibika", "inafanya"]) else "en"
    answer = brain.reply(text, lang)
    db.log("sms", f.get("From", "?"), lang, text, answer)
    return twiml(f"<Message>{html.escape(answer)}</Message>")


@app.route("audio/{name}", methods=["GET"])
def audio(req):
    path = os.path.join(tts.AUDIO, os.path.basename(req.route_params["name"]))
    return func.HttpResponse(open(path, "rb").read(), mimetype="audio/wav") if os.path.exists(path) else func.HttpResponse(status_code=404)


@app.route("events", methods=["GET"])
def events(req):
    return func.HttpResponse(json.dumps({"events": db.events(), "waterpoints": db.waterpoints()}), mimetype="application/json")


@app.route("dashboard", methods=["GET"])
def dashboard(req):
    return func.HttpResponse(open(os.path.join(os.path.dirname(__file__), "dashboard.html"), encoding="utf-8").read(), mimetype="text/html")
