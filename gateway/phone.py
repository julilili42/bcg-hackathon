"""Browser phone: Twilio Voice access tokens for web/src/Phone.tsx.
The browser calls Twilio over WebRTC; Twilio hits the TwiML App's voice URL, which is /api/voice.
Same pipeline as a real phone, only the microphone is the laptop's."""
import os, json, time, hmac, hashlib, base64


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
