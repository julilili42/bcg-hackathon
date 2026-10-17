"""Single-recipient outbound demo console. Only an explicit C key initiates a call."""
import fcntl
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import select
import sys
import tempfile
import termios
import time
import tty

# Support `python scripts/demo_call.py` from any working directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi import HTTPException
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client

import infrastructure as db
from voice import configuration, outbound_twiml

load_dotenv(ROOT / ".env")
FINAL = {"completed", "busy", "failed", "no-answer", "canceled"}
E164 = re.compile(r"\+[1-9]\d{7,14}\Z")


def settings():
    try:
        account, token, base = configuration()
    except HTTPException as exc:
        raise ValueError(exc.detail) from None
    sender = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    recipient = os.getenv("DEMO_CALLEE_NUMBER", "").strip()
    for name, number in (("TWILIO_PHONE_NUMBER", sender), ("DEMO_CALLEE_NUMBER", recipient)):
        if not E164.fullmatch(number):
            raise ValueError(f"Set {name} to a valid E.164 phone number in .env.")
    allowed = {n.strip() for n in os.getenv("DEMO_ALLOWED_NUMBERS", "").split(",") if n.strip()}
    if not allowed or any(not E164.fullmatch(n) for n in allowed):
        raise ValueError("Set DEMO_ALLOWED_NUMBERS to the explicitly consenting demo recipients in E.164 format.")
    if recipient not in allowed:
        raise ValueError("DEMO_CALLEE_NUMBER is not in DEMO_ALLOWED_NUMBERS; no call was placed.")
    if sender == recipient:
        raise ValueError("The demo recipient must differ from the Twilio sender number.")
    return account, token, base, sender, recipient


def prepare_opening():
    intro = "Hey, WaterLine here, your AI water assistant. "
    pipe_id = os.getenv("DEMO_OPENING_PIPE_ID", "").strip()
    if pipe_id:
        if not db.enabled():
            raise ValueError("A contextual opening requires DATABASE_URL.")
        pipe = db.get_pipe_by_id(pipe_id)
        if not pipe:
            raise ValueError("DEMO_OPENING_PIPE_ID does not identify an existing water point.")
        words = {"operational": "working", "broken": "broken", "low_flow": "delivering reduced flow",
                 "under_repair": "under repair", "unsafe": "unsafe", "unknown": "in an unknown condition"}
        condition = words.get(pipe["status"], "in an unknown condition")
        observed = pipe["status_observed_at"]
        freshness = "The latest saved report" if observed else "An undated saved report"
        opening = (intro + f"{freshness} describes {pipe['name']} in {pipe['village']} as {condition}. "
                   "It's unverified and may be out of date. ")
        if pipe["status"] != "operational":
            now = datetime.now(timezone.utc)
            alternatives = [p for p in db.get_pipes(pipe["village"], "operational")
                if str(p["id"]) != str(pipe_id) and p["status_observed_at"]
                and p["status_observed_at"] <= now]
            alternatives.sort(key=lambda p: p["status_observed_at"], reverse=True)
            if alternatives:
                other = alternatives[0]
                opening += f"{other['name']} is reported working as an alternative, also unverified. What would you like to know?"
            else:
                opening += "I don't have another dated working report in your village. What would you like to know?"
        else:
            opening += "What would you like to know?"
    else:
        opening = intro + (os.getenv("DEMO_OPENING_MESSAGE", "").strip() or
            "I can share water point updates or record a community report. How can I help?")
    if len(opening) > 1500:
        raise ValueError("The opening message is too long; keep it under fifteen hundred characters.")
    return opening, pipe_id or None


def masked(number):
    return "+" + "*" * max(4, len(number) - 5) + number[-4:]


def error_message(exc):
    # SDK error messages can contain the full recipient, request body, or URLs.
    if isinstance(exc, TwilioRestException):
        hints = {21211: "Check the destination number.", 21214: "Check the sender number.",
                 21215: "Enable calling for the destination country in Twilio Voice Geographic Permissions.",
                 21608: "Verify the demo recipient in your Twilio trial account.",
                 21219: "Verify the demo recipient in your Twilio trial account.",
                 20003: "Check the Twilio account credentials."}
        return f"Twilio error {exc.code}. " + hints.get(exc.code, "Check the Twilio call debugger.")
    return "The provider request could not be confirmed. Check Twilio before trying again."


def read_key(timeout=0.25):
    if not select.select([sys.stdin], [], [], timeout)[0]:
        return ""
    key = sys.stdin.read(1)
    return key.lower() if key else "q"


def run_console(client, config, key_reader=read_key, clock=time.monotonic, output=print):
    account, token, base, sender, recipient = config
    active = None
    last_status = None
    next_poll = 0
    uncertain = False
    output("========================================\n WATERLINE — DEMO CALL CONSOLE\n========================================")
    output(f"Demo recipient: {masked(recipient)}\n[c] Call demo user\n[q] Quit")
    while True:
        if active and clock() >= next_poll:
            next_poll = clock() + 2
            try:
                status = client.calls(active).fetch().status
                if status != last_status:
                    output(f"[CALL] Status: {status}")
                    last_status = status
                if status in FINAL:
                    active = None
                    output("[c] Call again when ready · [q] Quit")
            except Exception as exc:
                output("[CALL] Status unavailable. " + error_message(exc))
        key = key_reader()
        if key == "q":
            if active:
                output("Monitoring stopped; the existing phone call continues until hangup.")
            return
        if key != "c":
            continue
        if active or uncertain:
            output("[CALL] Dialing blocked while a call is active or its result is uncertain.")
            continue
        try:
            # Revalidate on every explicit action. No runtime HTTP dialing endpoint exists.
            if settings() != config:
                raise ValueError("Configuration changed. Restart the call console.")
            output("Preparing opening statement...")
            opening, pipe_id = prepare_opening()
            twiml = outbound_twiml(base, opening, pipe_id)
            # Also guard a restarted console against dialing over an existing demo call.
            recent = client.calls.list(to=recipient, from_=sender, limit=20)
            existing = next((call for call in recent if call.status not in FINAL), None)
            if existing:
                active, last_status = existing.sid, None
                output(f"[CALL] Already active; monitoring SID: {active}")
                continue
        except ValueError as exc:
            output(f"[CALL] {exc}")
            continue
        except Exception as exc:
            output("[CALL] Preparation failed; no new call requested. " + error_message(exc))
            continue
        output(f"Opening ready. Calling {masked(recipient)}...")
        try:
            call = client.calls.create(to=recipient, from_=sender, twiml=twiml, timeout=30, record=False)
            active, last_status = call.sid, call.status
            next_poll = clock() + 2
            output(f"[CALL] SID: {active}\n[CALL] Status: {last_status}")
            if last_status in FINAL:
                active = None
        except TwilioRestException as exc:
            # A server error may have happened after Twilio accepted the request.
            uncertain = exc.status >= 500
            output("[CALL] " + error_message(exc))
        except Exception as exc:
            uncertain = True  # Never retry a possibly accepted dial automatically.
            output("[CALL] " + error_message(exc))


def main():
    try:
        config = settings()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1
    # One controller per account on this computer; no database or new dependency.
    lock_name = hashlib.sha256(config[0].encode()).hexdigest()[:16]
    with open(Path(tempfile.gettempdir()) / f"waterline-demo-call-{lock_name}.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another WaterLine call console is already open.")
            return 1
        client = Client(config[0], config[1], http_client=TwilioHttpClient(timeout=15, max_retries=0))
        previous = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
        try:
            if previous:
                tty.setcbreak(sys.stdin.fileno())
            run_console(client, config)
        except KeyboardInterrupt:
            print("\nConsole closed; any connected call continues until hangup.")
        finally:
            if previous:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
