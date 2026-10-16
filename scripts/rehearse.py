#!/usr/bin/env python3
"""Run the demo script end to end against a running Reach API and print PASS/FAIL per step.

Usage: PYTHONPATH=api uv run python scripts/rehearse.py http://localhost:7071 [--reset]
       (or: scripts/with_server.py -- scripts/rehearse.py)
--reset clears live reports first through /api/admin/reset (needs ADMIN_TOKEN in the environment).
Simulates Twilio with the magic test numbers; nothing leaves this machine except calls to the API.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

PHONES = ["+15005550006", "+15005550007", "+15005550008"]  # Twilio magic numbers


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    ms: int = 0


@dataclass
class Run:
    base: str
    steps: list[Step] = field(default_factory=list)

    def get(self, path: str) -> object:
        with urllib.request.urlopen(f"{self.base}{path}", timeout=10) as resp:
            return json.loads(resp.read().decode())

    def post_form(self, path: str, data: dict[str, str]) -> str:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(f"{self.base}{path}", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode()

    def post_json(self, path: str, data: dict[str, object], headers: dict[str, str] | None = None) -> object:
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(data).encode(),
            method="POST",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def step(self, name: str, fn: object) -> None:
        start = time.perf_counter()
        try:
            detail = fn() if callable(fn) else ""
            ok, text = detail if isinstance(detail, tuple) else (True, str(detail or ""))
        except Exception as exc:  # noqa: BLE001 - a rehearsal step reports, never crashes
            ok, text = False, f"{type(exc).__name__}: {exc}"
        self.steps.append(Step(name, bool(ok), str(text), int((time.perf_counter() - start) * 1000)))
        ms = int((time.perf_counter() - start) * 1000)
        print(f"{'PASS' if ok else 'FAIL'}  {name:46s} {ms:5d} ms  {text}")


def find_feature(fc: object, alias: str) -> dict[str, object] | None:
    assert isinstance(fc, dict)
    for feature in fc.get("features", []):
        props = feature["properties"]
        if alias == props["name"] or alias in props.get("aliases", []):
            return feature
    return None


def main(argv: list[str]) -> int:
    base = next(
        (a for a in argv if a.startswith("http")), os.environ.get("BASE_URL", "http://localhost:7071")
    ).rstrip("/")
    run = Run(base)
    print(f"Rehearsal against {base}\n")

    if "--reset" in argv:
        token = os.environ.get("ADMIN_TOKEN", "")

        def reset() -> tuple[bool, str]:
            if not token:
                return False, "ADMIN_TOKEN not set"
            out = run.post_json("/api/admin/reset?mode=live", {}, {"X-Admin-Token": token})
            return True, f"{out}"

        run.step("0 reset live reports", reset)

    state: dict[str, object] = {}

    def step1() -> tuple[bool, str]:
        fc = run.get("/api/entities?domain=water")
        stats = run.get("/api/stats?domain=water")
        assert isinstance(fc, dict) and isinstance(stats, dict)
        shule, kanisa = find_feature(fc, "Shule"), find_feature(fc, "Kanisa")
        state["shule"], state["kanisa"] = shule, kanisa
        ok = len(fc["features"]) >= 300 and shule is not None and kanisa is not None
        return (
            ok,
            f"{len(fc['features'])} points, {stats['people_affected']:,} people behind non-working points",
        )

    run.step("1 map shows Kisarawe with Shule and Kanisa", step1)

    def step2() -> tuple[bool, str]:
        greeting = run.post_form("/api/voice", {"From": PHONES[0], "CallSid": "CA1"})
        assert 'language="sw-TZ"' in greeting, "no Swahili gather"
        reply = run.post_form(
            "/api/voice/handle?lang=sw&domain=water",
            {"From": PHONES[0], "CallSid": "CA1", "SpeechResult": "Kisima cha Shule hakifanyi kazi"},
        )
        ok = "imeandikwa kama imeharibika" in reply and "Kanisa" in reply and "<Hangup/>" in reply
        spoken = reply.split("<Say>")[-1].split("</Say>")[0] if "<Say>" in reply else "(audio)"
        return ok, spoken[:110]

    run.step("2 call: Shule reported broken, alternative spoken", step2)

    def step3() -> tuple[bool, str]:
        shule = state.get("shule")
        assert isinstance(shule, dict)
        detail = run.get(f"/api/entities/{urllib.parse.quote(str(shule['id']))}")
        assert isinstance(detail, dict)
        props = detail["entity"]["properties"]
        feed = run.get("/api/reports?domain=water&limit=5")
        assert isinstance(feed, list)
        in_feed = any(r["entity_id"] == shule["id"] for r in feed)
        ok = props["current_status"] == "broken" and props["verified"] and in_feed
        summary = f"status={props['current_status']} confidence={props['confidence']}"
        return ok, f"{summary} verified={props['verified']} in_feed={in_feed}"

    run.step("3 map: Shule red, verified, in the feed", step3)

    def step4() -> tuple[bool, str]:
        reply = run.post_form("/api/sms", {"From": PHONES[0], "Body": "Is Shule working?"})
        ok = "Shule is broken" in reply and "minutes on foot" in reply
        return ok, reply.split("<Message>")[-1].split("</Message>")[0][:110]

    run.step("4 sms (en): query answered with alternative", step4)

    def step5() -> tuple[bool, str]:
        second = run.post_form("/api/sms", {"From": PHONES[1], "Body": "Shule inafanya kazi"})
        disputed = "zinazopingana" in second
        third = run.post_form("/api/sms", {"From": PHONES[2], "Body": "Shule imeharibika"})
        resolved = "imeandikwa kama imeharibika" in third
        return disputed and resolved, f"disputed={disputed} resolved={resolved}"

    run.step("5 conflict: 2nd phone disputes, 3rd resolves", step5)

    def step5b() -> tuple[bool, str]:
        ask = run.post_form("/api/sms", {"From": PHONES[1], "Body": "hakuna maji"})
        asked = "Kisima gani?" in ask
        done = run.post_form("/api/sms", {"From": PHONES[1], "Body": "Bwawa"})
        recorded = "Bwawa imeandikwa kama haina maji" in done
        return asked and recorded, f"asked={asked} recorded={recorded}"

    run.step("5b follow-up: 'hakuna maji' -> which point? -> Bwawa", step5b)

    def step6() -> tuple[bool, str]:
        reply = run.post_form("/api/sms", {"From": PHONES[0], "Body": "Zahanati Msanga imefungwa"})
        fc = run.get("/api/entities?domain=health")
        msanga = find_feature(fc, "Zahanati Msanga")
        ok = (
            "imeandikwa kama imefungwa" in reply
            and msanga is not None
            and msanga["properties"]["current_status"] == "closed"
        )
        return ok, reply.split("<Message>")[-1].split("</Message>")[0][:110]

    run.step("6 clinics: same number, Msanga closed, alternative", step6)

    def step7() -> tuple[bool, str]:
        talk = run.get("/api/interactions?limit=10")
        stats = run.get("/api/stats?domain=water")
        assert isinstance(talk, list) and isinstance(stats, dict)
        ok = len(talk) >= 5 and stats["reports_24h"] >= 3 and stats["verified"] >= 1
        summary = f"{len(talk)} conversations, {stats['reports_24h']} reports today"
        return ok, f"{summary}, {stats['verified']} verified points"

    run.step("7 dashboard: conversations and stats updated", step7)

    def step8() -> tuple[bool, str]:
        health = run.get("/api/health")
        assert isinstance(health, dict)
        note = "(demo must also pass with keywords/none)"
        return True, f"understanding={health['understanding']} tts={health['tts']} {note}"

    run.step("8 configuration in use", step8)

    total = sum(s.ms for s in run.steps)
    failed = [s for s in run.steps if not s.ok]
    print(f"\n{len(run.steps) - len(failed)}/{len(run.steps)} steps passed in {total} ms")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
