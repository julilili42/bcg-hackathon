// Real Nokia 3310 photo as chassis; a real call through Twilio Voice SDK -> TwiML App -> /api/voice.
// Navi key = call, C = hang up / clear, digits = DTMF during a call (language menu: 1 sw, 2 en, 3 de). Middle: the map, right: the live water points
// and the callers who said where they stand and which water point they cannot get water from (incidents).
import { useEffect, useRef, useState } from "react";
import { Call, Device } from "@twilio/voice-sdk";
import { COLOR, age, distanceKm, useEvents, walkMinutes, type LogEvent } from "./api";
import { CLEAR, DIGITS, LCD, NAVI, ROCKER } from "./hits";
import WaterMap from "./WaterMap";

type Line = string | [cls: "big" | "blink", text: string];
type Lcd = { lines: Line[]; status: string; soft: string; on: boolean };

const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const pretty = (n: string) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3");
const spaced = (n: string) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "+1 $1 $2 $3");
const wrap = (text: string, width: number): Line[] => {  // three LCD lines, word-wrapped, the rest cut
  const lines: string[] = [];
  for (const word of text.split(/\s+/)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && (last + " " + word).length <= width) lines[lines.length - 1] = last + " " + word;
    else lines.push(word.slice(0, width));
  }
  return lines.slice(0, 3);
};

export default function Phone() {
  const [lcd, setLcd] = useState<Lcd>({ lines: [["big", "NOKIA"], "WaterLine", "loading"], status: "", soft: "", on: false });
  const [number, setNumber] = useState("+18654598142");
  const [inCall, setInCall] = useState(false);
  const [pressed, setPressed] = useState("");
  const [errors, setErrors] = useState<{ who: string; text: string }[]>([]);
  const data = useEvents(2000);
  // the call machine lives in refs: event handlers and timers must see the current call, not a stale render
  const device = useRef<Device | null>(null);
  const call = useRef<Call | null>(null);
  const num = useRef(number);
  const dialed = useRef("");
  const startedAt = useRef(0);
  const tick = useRef(0);

  const show = (lines: Line[], status = "", soft = "Call") => setLcd((l) => ({ ...l, lines, status, soft }));
  const err = (who: string, text: string) => setErrors((e) => [{ who, text }, ...e]);
  const idle = (lines?: Line[]) => { setInCall(false); show(lines ?? [["big", dialed.current || pretty(num.current)], "WaterLine"]); };
  const elapsed = () => fmt(Math.round((Date.now() - startedAt.current) / 1000));

  async function dial() {
    if (!device.current || call.current) return;
    show([["big", pretty(num.current)], ["blink", "Calling..."], "allow mic"], "", "End");
    try {
      call.current = await device.current.connect({ params: { To: num.current } });
    } catch (e) {
      call.current = null; idle(["Call failed", "see panel", "Navi = retry"]); err("Call", (e as Error).message); return;
    }
    setInCall(true);
    call.current.on("accept", () => {
      startedAt.current = Date.now();
      tick.current = window.setInterval(() => show([["big", pretty(num.current)], elapsed(), "speak / 1 sw 2 en 3 de"], "", "End"), 1000);
    });
    for (const ev of ["disconnect", "cancel", "reject"]) call.current.on(ev, hangup);
  }

  function hangup() {
    try { call.current?.disconnect(); } catch { /* already gone */ }
    call.current = null;
    clearInterval(tick.current);
    idle(["Call ended"]);
  }

  function key(d: string) {
    if (call.current) { call.current.sendDigits(d); show([["big", pretty(num.current)], elapsed(), `sent ${d}`], "", "End"); return; }
    dialed.current = (dialed.current + d).slice(-14);
    show([["big", dialed.current], "only the line"]);
  }

  const clear = () => { if (call.current) hangup(); else { dialed.current = ""; idle(); } };

  useEffect(() => {
    (async () => {
      const r = await fetch("/api/phone/token");
      if (!r.ok) { show(["Setup missing", "run scripts/", "phone_setup.py"], "!", ""); err("Setup", await r.text()); return; }
      const d: { token: string; number: string } = await r.json();
      if (d.number) { num.current = d.number; setNumber(d.number); }
      const dev = new Device(d.token, { codecPreferences: [Call.Codec.Opus, Call.Codec.PCMU], closeProtection: true });
      dev.on("error", (e: { code?: number; message: string }) => { show(["Error", e.code ? `code ${e.code}` : "", "see panel"], "!"); err("Twilio", e.message); });
      dev.on("tokenWillExpire", async () => dev.updateToken((await (await fetch("/api/phone/token")).json()).token));
      device.current = dev;
      setLcd((l) => ({ ...l, on: true }));
      idle();
    })().catch((e: Error) => { show(["Error", "see panel"], "!", ""); err("Init", e.message); });
  }, []);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (/^[0-9*#]$/.test(ev.key)) { key(ev.key); setPressed(ev.key); setTimeout(() => setPressed(""), 120); }
      else if (ev.key === "Enter") dial();
      else if (ev.key === "Escape") clear();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const HOT_S = 120;   // rows touched by a call in the last two minutes stand out
  const FOCUS_S = 30;  // the map stays on the newest of them for half a minute, then glides back to the overview
  const agoS = (ts: string) => (Date.now() - new Date(String(ts).replace(" ", "T") + "Z").getTime()) / 1000;
  const hotPoints = data.waterpoints.filter((w) => agoS(w.updated) < HOT_S).sort((a, b) => agoS(a.updated) - agoS(b.updated));
  const incidents = data.incidents.filter((r) => agoS(r.ts) < HOT_S);  // newest first; the water points they touch are hot too
  const hot = new Set([...hotPoints.map((w) => w.id), ...incidents.flatMap((r) => [r.wp_id, r.alt_id ?? -1])]);
  const blockedIds = new Set(incidents.filter((r) => r.blocked).map((r) => r.wp_id));
  const incident = incidents[0] && agoS(incidents[0].ts) < FOCUS_S ? incidents[0] : null;  // a located caller wins the map over a plain status change
  const focus = !incident && hotPoints[0] && agoS(hotPoints[0].updated) < FOCUS_S ? hotPoints[0] : null;
  const byId = Object.fromEntries(data.waterpoints.map((w) => [w.id, w]));
  const debug = location.search.includes("debug"); // ?debug=1 shows the hit areas

  // an SMS arrives: the phone buzzes, the LCD says "1 message received", then shows it, then goes back to idle
  const [buzz, setBuzz] = useState(false);
  const [last, setLast] = useState<LogEvent | null>(null);
  const seen = useRef<string | null>(null);  // newest event id of the last poll; null = first poll, nothing is new
  const timers = useRef<number[]>([]);
  useEffect(() => {
    const ids = data.events.map((e) => e.id);
    if (!ids.length) return;
    if (seen.current === null) { seen.current = ids[0]; return; }
    const fresh = data.events.slice(0, Math.max(0, ids.indexOf(seen.current))).filter((e) => e.channel === "sms");
    seen.current = ids[0];
    if (!fresh.length) return;
    setLast(fresh[0]);  // the example under TEXT ME becomes the real exchange
    if (call.current) return;  // during a call the display belongs to the call
    setBuzz(true); setTimeout(() => setBuzz(false), 700);
    show([["big", `${fresh.length} message${fresh.length > 1 ? "s" : ""}`], "received"], "✉", "");
    for (const t of timers.current) clearTimeout(t);  // a second SMS restarts the sequence; the poll must not cancel it
    timers.current = [setTimeout(() => show(wrap(fresh[0].body, 17), "✉", ""), 2200),
                      setTimeout(() => { if (!call.current) idle(); }, 7000)];
  }, [data.events]);

  return (
    <div className={`stage${debug ? " debug" : ""}`}>
      <div className="left">
      <div className="call-me"><span className="cta">text me</span><span className="num">{spaced(number)}</span>
        <div className="eg">
          <span className="sent">{last ? last.body : "Zahanati is broken"}</span>
          <span className="got">{last ? last.reply : "Recorded: Zahanati broken. Nearest working: Mama Nasa, ~15 min on foot."}</span>
        </div></div>
      <div className={`phone${buzz ? " buzz" : ""}`}>
        <img src={`${import.meta.env.BASE_URL}nokia3310.png`} alt="Nokia 3310" draggable={false} />
        <div className={`lcd${lcd.on ? " on" : ""}`} style={LCD} aria-live="polite">
          <div className="lcd-top"><span className="sig">▮▮▮▮</span><span>{lcd.status}</span><span className="bat">▮▮▮</span></div>
          <div className="lcd-main">
            {lcd.lines.map((l, i) => { const [cls, text] = typeof l === "string" ? ["", l] : l; return <div key={i} className={cls}>{text}</div>; })}
          </div>
          <div className="lcd-soft">{lcd.soft}</div>
        </div>
        <button className={`hit navi${inCall ? " live" : ""}`} style={NAVI} aria-label="Call" onClick={() => !call.current && dial()} />
        <button className="hit" style={CLEAR} aria-label="Hang up or clear" onClick={clear} />
        <div className="rocker" style={ROCKER}><button className="hit" aria-label="Previous" /><button className="hit" aria-label="Next" /></div>
        {DIGITS.map(([d, style]) => (
          <button key={d} className={`hit${pressed === d ? " pressed" : ""}`} style={style} onClick={() => key(d)}>{d}</button>
        ))}
      </div>
      </div>

      <section className="mapbox" aria-label="Map">
        <WaterMap waterpoints={data.waterpoints} focus={focus} incident={incident} className="panel-map" />
      </section>

      <aside className="panel" aria-label="Live data">
        {incidents.length > 0 && <>
          <h2>Callers</h2>
          <ol className="log callers">{incidents.map((r) => {
            const wp = byId[r.wp_id], alt = r.alt_id == null ? undefined : byId[r.alt_id];
            return <li key={r.id} className={r.id === incident?.id ? "live" : ""} style={{ borderColor: r.blocked || !wp ? COLOR.broken : COLOR[wp.status] }}>
              <div className="who">{r.blocked ? "way blocked" : wp?.status} · {age(r.ts)}</div>
              <div className="line"><b>{r.place}</b> → {wp?.name ?? "?"}{alt && <> · go to <b>{alt.name}</b>, ~{walkMinutes(distanceKm(r, alt))} min</>}</div>
            </li>;
          })}</ol>
        </>}
        <h2>Water points</h2>
        <div className="scroll"><table className="wp">
          <tbody>{data.waterpoints.map((w) => (
            <tr key={w.id} className={hot.has(w.id) ? "hot" : ""}>
              <td><div>{w.name}</div><div className="sub">{w.village} · {age(w.updated)}{blockedIds.has(w.id) && <span className="blocked"> · way blocked</span>}</div></td>
              <td className={`status ${w.status}`}>{w.status}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {errors.length > 0 && <ol className="log">
          {errors.map((e, i) => <li key={i} className="error"><div className="who">{e.who}</div><div className="line">{e.text}</div></li>)}
        </ol>}
      </aside>
    </div>
  );
}
