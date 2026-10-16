"""Understand one utterance, update the water point table, produce the reply text.
Claude when ANTHROPIC_API_KEY is set, keyword matching otherwise. Both return the same dict."""
import os, json
from . import db

MENU = [("sw", "Kwa Kiswahili, bonyeza moja."), ("en", "For English, press two."), ("de", "Für Deutsch, drücken Sie die Drei.")]
T = {  # reply templates. ponytail: Swahili written by non-native, have a Tanzanian read it once.
    "sw": {"greet": "Karibu. Sema jina la kisima na hali yake.",
           "unknown": "Samahani, sikuelewa. Tafadhali sema jina la kisima.",
           "again": "Tafadhali sema tena jina la kisima.",
           "confirm": "Ulisema {p}? Bonyeza moja kwa ndiyo, mbili kusema tena.",
           "another": "Kuripoti kisima kingine, bonyeza moja.",
           "bye": "Kwaheri.",
           "recorded": "Asante. {p} imeandikwa kama {s}.",
           "status": "{p} {s}.",
           "nearest": " Kisima cha karibu kinachofanya kazi ni {q}, dakika {m} kwa miguu.",
           "none": " Hakuna kisima kinachofanya kazi karibu.",
           "s": {"ok": "inafanya kazi", "broken": "imeharibika", "empty": "haina maji"}},
    "en": {"greet": "Welcome. Say the name of the water point and whether it works.",
           "unknown": "Sorry, I did not understand. Please say the name of the water point.",
           "again": "Please say the name of the water point again.",
           "confirm": "Did you say {p}? Press 1 for yes, 2 to say it again.",
           "another": "To report another water point, press 1.",
           "bye": "Goodbye.",
           "recorded": "Thank you. {p} is recorded as {s}.",
           "status": "{p} is {s}.",
           "nearest": " The nearest working water point is {q}, {m} minutes on foot.",
           "none": " There is no working water point nearby.",
           "s": {"ok": "working", "broken": "broken", "empty": "empty"}},
    "de": {"greet": "Willkommen. Sagen Sie den Namen der Wasserstelle und ob sie funktioniert.",
           "unknown": "Entschuldigung, das habe ich nicht verstanden. Bitte sagen Sie den Namen der Wasserstelle.",
           "again": "Bitte sagen Sie noch einmal den Namen der Wasserstelle.",
           "confirm": "Meinten Sie {p}? Drücken Sie 1 für ja, 2 zum Wiederholen.",
           "another": "Um eine weitere Wasserstelle zu melden, drücken Sie 1.",
           "bye": "Auf Wiederhören.",
           "recorded": "Danke. {p} ist als {s} gespeichert.",
           "status": "{p} ist {s}.",
           "nearest": " Die nächste funktionierende Wasserstelle ist {q}, {m} Minuten zu Fuß.",
           "none": " In der Nähe gibt es keine funktionierende Wasserstelle.",
           "s": {"ok": "in Betrieb", "broken": "kaputt", "empty": "leer"}},
}
STATUS_WORDS = {"broken": ["broken", "not work", "damaged", "imeharibika", "haifanyi", "mbovu", "kaputt", "defekt", "funktioniert nicht"],
                "empty": ["empty", "dry", "no water", "hakuna maji", "kavu", "haina maji", "leer", "kein wasser", "trocken"],
                "ok": ["working", "works", "fine", "inafanya kazi", "nzuri", "iko sawa", "funktioniert", "geht wieder", "läuft"]}
LANG_WORDS = {"sw": ["kisima", "maji", "imeharibika", "inafanya", "kazi"], "de": ["wasserstelle", "brunnen", "kaputt", "funktioniert", "ist "]}


def understand(text, lang=None):
    """-> {"point": name|None, "status": ok|broken|empty|None, "lang": sw|en|de}. status None = caller is asking."""
    points = db.waterpoints()
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _claude(text, [p["name"] for p in points])
        except Exception as e:  # ponytail: any API trouble -> keywords, the caller still gets an answer
            print("claude failed, using keywords:", e)
    low = text.lower()
    point = next((p["name"] for p in points if p["name"].lower() in low), None)
    status = next((s for s, words in STATUS_WORDS.items() if any(w in low for w in words)), None)
    guess = next((l for l, words in LANG_WORDS.items() if any(w in low for w in words)), "en")
    return {"point": point, "status": status, "lang": lang or guess}


def _claude(text, names):
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model="claude-opus-5-5", max_tokens=256, output_config={"effort": "low"},
        system="A caller to a rural water hotline said one sentence, in Swahili, English or German, possibly garbled by speech recognition. "
               f"Known water points: {names}. Match the name loosely (spelling, case, partial). "
               'Answer with JSON only: {"point": <known name or null>, "status": "ok"|"broken"|"empty"|null, "lang": "sw"|"en"|"de"}. '
               "status is null when the caller asks instead of reporting. broken = pump damaged; empty = no water.",
        messages=[{"role": "user", "content": text}])
    out = json.loads(next(b.text for b in r.content if b.type == "text").strip().strip("`").removeprefix("json"))
    return {"point": out.get("point"), "status": out.get("status"), "lang": out.get("lang") or "en"}


def reply(text, lang=None):
    """The whole loop: understand -> update -> answer. Every caller gets an answer, also the one reporting.
    lang None (SMS) = answer in the language the message was written in."""
    u = understand(text, lang)
    return answer(u, lang or u["lang"])


def answer(u, lang):
    """Update the table from an understood utterance and build the spoken reply. -> (text, lang)"""
    t = T[lang]
    points = db.waterpoints()
    p = next((x for x in points if x["name"] == u["point"]), None)
    if not p:
        return t["unknown"], lang
    if u["status"]:
        db.set_status(p["id"], u["status"])
        p["status"] = u["status"]
        out = t["recorded"].format(p=p["name"], s=t["s"][p["status"]])
    else:
        out = t["status"].format(p=p["name"], s=t["s"][p["status"]])
    if p["status"] != "ok":
        ok = [(db.walk_minutes(p, q), q) for q in points if q["status"] == "ok" and q["id"] != p["id"]]
        m, q = min(ok, key=lambda x: x[0]) if ok else (None, None)  # key: ties must not compare the dicts
        out += t["nearest"].format(q=q["name"], m=m) if ok else t["none"]
    return out, lang


if __name__ == "__main__":  # self-check, keyword path
    os.environ.pop("ANTHROPIC_API_KEY", None)
    assert "Mama Nasa" in reply("the Zahanati well is broken", "en")[0]
    assert reply("Zahanati imeharibika") == (reply("Zahanati imeharibika")[0], "sw")
    assert reply("blah", "en")[0] == T["en"]["unknown"]
    assert reply("Mushi ist kaputt") == (reply("Mushi ist kaputt")[0], "de") and "kaputt" in reply("Mushi ist kaputt")[0]
    print("brain ok")
