"""Browser phone: serves phone/index.html and hands out Twilio Voice access tokens.
The browser calls Twilio over WebRTC; Twilio hits the TwiML App's voice URL, which is /api/voice.
Same pipeline as a real phone, only the microphone is the laptop's."""
import os, json, time, hmac, hashlib, base64, mimetypes
import azure.functions as func

bp = func.Blueprint()
HERE = os.path.dirname(__file__)


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def access_token(identity, ttl=3600):
    """Twilio Access Token with a Voice grant: a HS256 JWT signed with the API key secret."""
    key, secret = os.environ["TWILIO_API_KEY"], os.environ["TWILIO_API_SECRET"]
    now = int(time.time())
    header = {"typ": "JWT", "alg": "HS256", "cty": "twilio-fpa;v=1"}
    claims = {"jti": f"{key}-{now}", "iss": key, "sub": os.environ["TWILIO_ACCOUNT_SID"],
              "iat": now, "nbf": now, "exp": now + ttl,
              "grants": {"identity": identity,
                         "voice": {"outgoing": {"application_sid": os.environ["TWILIO_APP_SID"]},
                                   "incoming": {"allow": False}}}}
    body = ".".join(_b64(json.dumps(p, separators=(",", ":")).encode()) for p in (header, claims))
    return body + "." + _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


@bp.route("phone/token", methods=["GET"])
def token(req):
    if not os.environ.get("TWILIO_API_KEY"):
        return func.HttpResponse("Browser phone not set up: run `uv run phone/setup.py`", status_code=503)
    identity = req.params.get("identity", "demo")[:32]
    return func.HttpResponse(json.dumps({"token": access_token(identity), "number": os.environ.get("TWILIO_NUMBER", "")}),
                             mimetype="application/json")


@bp.route("phone", methods=["GET"])
def phone(req):
    return _static("index.html")


@bp.route("phone/static/{name}", methods=["GET"])
def phone_asset(req):
    return _static(req.route_params["name"])


def _static(name):
    path = os.path.join(HERE, os.path.basename(name))
    if not os.path.isfile(path):
        return func.HttpResponse(status_code=404)
    return func.HttpResponse(open(path, "rb").read(), mimetype=mimetypes.guess_type(path)[0] or "application/octet-stream")
