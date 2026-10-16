"""Understand one utterance, update the water point table, produce the reply text.
Azure OpenAI when configured, keyword matching otherwise. Both return the same dict."""
import os, json, re, urllib.request
import db

T = {  # reply templates. ponytail: Swahili written by non-native, have a Tanzanian read it once.
    "sw": {"greet": "Karibu. Sema jina la kisima na hali yake. Kwa Kiingereza, bonyeza mbili.",
           "unknown": "Samahani, sikuelewa. Tafadhali sema jina la kisima.",
           "recorded": "Asante. {p} imeandikwa kama {s}.",
           "status": "{p} {s}.",
           "nearest": " Kisima cha karibu kinachofanya kazi ni {q}, dakika {m} kwa miguu.",
           "none": " Hakuna kisima kinachofanya kazi karibu.",
           "s": {"ok": "inafanya kazi", "broken": "imeharibika", "empty": "haina maji"}},
    "en": {"greet": "Welcome. Say the name of the water point and whether it works.",
           "unknown": "Sorry, I did not understand. Please say the name of the water point.",
           "recorded": "Thank you. {p} is recorded as {s}.",
           "status": "{p} is {s}.",
           "nearest": " The nearest working water point is {q}, {m} minutes on foot.",
           "none": " There is no working water point nearby.",
           "s": {"ok": "working", "broken": "broken", "empty": "empty"}},
}
STATUS_WORDS = {"broken": ["broken", "not work", "damaged", "imeharibika", "haifanyi", "mbovu"],
                "empty": ["empty", "dry", "no water", "hakuna maji", "kavu", "haina maji"],
                "ok": ["working", "works", "fine", "inafanya kazi", "nzuri", "iko sawa"]}


def understand(text, lang):
    """-> {"point": name|None, "status": ok|broken|empty|None}. status None = caller is asking."""
    points = db.waterpoints()
    if os.environ.get("AZURE_OPENAI_KEY"):
        return _llm(text, [p["name"] for p in points])
    low = text.lower()
    point = next((p["name"] for p in points if p["name"].lower() in low), None)
    status = next((s for s, words in STATUS_WORDS.items() if any(w in low for w in words)), None)
    return {"point": point, "status": status}


def _llm(text, names):
    body = {"messages": [
        {"role": "system", "content": "Extract from a caller's sentence (Swahili or English) the water point name and its status. "
         f"Known water points: {names}. Reply JSON {{\"point\": name or null, \"status\": \"ok\"|\"broken\"|\"empty\"|null}}. "
         "status null means the caller is asking, not reporting."},
        {"role": "user", "content": text}], "response_format": {"type": "json_object"}, "temperature": 0}
    url = f"{os.environ['AZURE_OPENAI_ENDPOINT']}/openai/deployments/{os.environ['AZURE_OPENAI_DEPLOYMENT']}/chat/completions?api-version=2024-10-21"
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "api-key": os.environ["AZURE_OPENAI_KEY"]})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(json.load(r)["choices"][0]["message"]["content"])


def reply(text, lang):
    """The whole loop: understand -> update -> answer. Every caller gets an answer, also the one reporting."""
    t = T[lang]
    u = understand(text, lang)
    points = db.waterpoints()
    p = next((x for x in points if x["name"] == u["point"]), None)
    if not p:
        return t["unknown"]
    if u["status"]:
        db.set_status(p["id"], u["status"])
        p["status"] = u["status"]
        out = t["recorded"].format(p=p["name"], s=t["s"][p["status"]])
    else:
        out = t["status"].format(p=p["name"], s=t["s"][p["status"]])
    if p["status"] != "ok":
        ok = [(db.walk_minutes(p, q), q) for q in points if q["status"] == "ok" and q["id"] != p["id"]]
        out += t["nearest"].format(q=min(ok)[1]["name"], m=min(ok)[0]) if ok else t["none"]
    return out


if __name__ == "__main__":  # self-check, keyword path
    assert "Shule" in reply("the Shule well is broken", "en")
    assert "Kanisa" in reply("Shule imeharibika", "sw")
    assert reply("blah", "en") == T["en"]["unknown"]
    print("brain ok")
