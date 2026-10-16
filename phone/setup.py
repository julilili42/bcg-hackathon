"""One-time Twilio setup for the browser phone: an API key (signs access tokens) and a TwiML App
(tells Twilio which webhook to hit when the browser calls). Writes the ids into local.settings.json.
Run: uv run phone/setup.py"""
import json, os, base64, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(HERE, "local.settings.json")
cfg = json.load(open(SETTINGS))
V = cfg["Values"]
SID, TOK = V["TWILIO_ACCOUNT_SID"], V["TWILIO_AUTH_TOKEN"]
API = f"https://api.twilio.com/2010-04-01/Accounts/{SID}"


def post(path, **data):
    req = urllib.request.Request(f"{API}/{path}.json", urllib.parse.urlencode(data).encode() if data else None)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{SID}:{TOK}".encode()).decode())
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{path}: {e.code} {e.read().decode()[:300]}")


def save():
    json.dump(cfg, open(SETTINGS, "w"), indent=2)


if not V.get("TWILIO_API_KEY"):
    k = post("Keys", FriendlyName="reach-gateway browser phone")
    V["TWILIO_API_KEY"], V["TWILIO_API_SECRET"] = k["sid"], k["secret"]
    save()  # the secret is shown exactly once
    print("API key", k["sid"])
if not V.get("TWILIO_APP_SID"):
    a = post("Applications", FriendlyName="reach-gateway browser phone", VoiceMethod="POST")
    V["TWILIO_APP_SID"] = a["sid"]
    save()
    print("TwiML app", a["sid"], "(voice url is set by set_webhooks.sh)")
if not V.get("TWILIO_NUMBER"):
    nums = post("IncomingPhoneNumbers")["incoming_phone_numbers"]
    if nums:
        V["TWILIO_NUMBER"] = nums[0]["phone_number"]
        save()
        print("number", V["TWILIO_NUMBER"])
print("ok")
