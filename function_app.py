"""Twilio-Webhooks (SMS + Voice) -> events-Tabelle -> Dashboard.
handle() ist der einzige Ort, der sich ändert, wenn die Idee steht."""
import json, html, os
import azure.functions as func
import db

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
XML = "text/xml"


def handle(text: str) -> str:
    """ponytail: Echo. In Stunde 4 durch den echten Parser ersetzen."""
    return f"Received: {text}"


def twiml(inner: str) -> func.HttpResponse:
    return func.HttpResponse(f"<Response>{inner}</Response>", mimetype=XML)


@app.route("sms", methods=["POST"])
def sms(req: func.HttpRequest) -> func.HttpResponse:
    f = req.form
    db.store("sms", f.get("From", "?"), f.get("Body", ""))
    return twiml(f"<Message>{html.escape(handle(f.get('Body', '')))}</Message>")


@app.route("voice", methods=["POST"])
def voice(req: func.HttpRequest) -> func.HttpResponse:
    f = req.form
    if f.get("Digits"):  # zweiter Request, nach Tastendruck
        db.store("voice", f.get("From", "?"), f["Digits"])
        return twiml(f"<Say>{html.escape(handle(f['Digits']))}</Say>")
    return twiml("<Gather numDigits='1'><Say>Press 1 for price, 2 for water.</Say></Gather>"
                 "<Say>No input received.</Say>")


@app.route("events", methods=["GET"])
def events(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(db.recent()), mimetype="application/json")


@app.route("dashboard", methods=["GET"])
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), encoding="utf-8") as fh:
        return func.HttpResponse(fh.read(), mimetype="text/html")
