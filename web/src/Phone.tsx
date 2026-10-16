// Real Nokia 3310 photo as chassis; a real call through Twilio Voice SDK -> TwiML App -> /api/voice.
// Navi key = call, C = hang up / clear, digits = DTMF during a call (language menu: 1 sw, 2 en, 3 de). Right side: the live database.
import { useEffect, useMemo, useRef, useState } from "react";
import { Call, Device } from "@twilio/voice-sdk";
import { age, useEvents } from "./api";
import { CLEAR, DIGITS, LCD, NAVI, ROCKER } from "./hits";

type Line = string | [cls: "big" | "blink", text: string];
type Lcd = { lines: Line[]; status: string; soft: string; on: boolean };

const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const pretty = (n: string) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3");
const spaced = (n: string) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "+1 $1 $2 $3");

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
  const idle = (lines?: Line[]) => { setInCall(false); show(lines ?? [["big", dialed.current || pretty(num.current)], "WaterLine", "Navi = call"]); };
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
    idle(["Call ended", "Navi = call"]);
  }

  function key(d: string) {
    if (call.current) { call.current.sendDigits(d); show([["big", pretty(num.current)], elapsed(), `sent ${d}`], "", "End"); return; }
    dialed.current = (dialed.current + d).slice(-14);
    show([["big", dialed.current], "only the line", "Navi = call"]);
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

  const last = useRef<Record<number, string>>({});
  const changed = useMemo(() => {  // rows whose status changed since the last poll flash once
    const c = new Set<number>();
    for (const w of data.waterpoints) { if (last.current[w.id] && last.current[w.id] !== w.status) c.add(w.id); last.current[w.id] = w.status; }
    return c;
  }, [data]);
  const calls = data.events.filter((e) => e.channel === "voice").slice(0, 3);
  const HOT_S = 120;  // rows touched by a call in the last two minutes stand out, the rest dims
  const agoS = (ts: string) => (Date.now() - new Date(String(ts).replace(" ", "T") + "Z").getTime()) / 1000;
  const hot = new Set(data.waterpoints.filter((w) => agoS(w.updated) < HOT_S).map((w) => w.id));
  const debug = location.search.includes("debug"); // ?debug=1 shows the hit areas

  return (
    <div className={`stage${debug ? " debug" : ""}`}>
      <div className="phone">
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

      <aside className="panel" aria-label="Live data">
        <header><h1>WaterLine</h1><div className="call-me"><span className="cta">give me a call</span><span className="num">{spaced(number)}</span></div></header>
        <section>
          <h2>Water points <span className="live-dot" title="live" /><span className="hint">live, every 2 s</span></h2>
          <table className={`wp${hot.size ? " focus" : ""}`}>
            <thead><tr><th>Name</th><th>Village</th><th>Status</th><th>Updated</th></tr></thead>
            <tbody>{data.waterpoints.map((w) => (
              <tr key={w.id} className={`${hot.has(w.id) ? "hot" : ""}${changed.has(w.id) ? " changed" : ""}`}>
                <td>{w.name}</td><td>{w.village}</td><td className={`status ${w.status}`}>{w.status}</td><td className="age">{age(w.updated)}</td>
              </tr>
            ))}</tbody>
          </table>
        </section>
        <details className="calls">
          <summary><h2>Last calls <span className="hint">Navi = call · C = hang up · 1 sw · 2 en · 3 de</span></h2></summary>
          <ol className="log">
            {errors.map((e, i) => <li key={`e${i}`} className="error"><div className="who">{e.who}</div><div className="line">{e.text}</div></li>)}
            {!calls.length && <li className="empty">No calls yet.</li>}
            {calls.map((e) => (
              <li key={e.id}>
                <div className="who">{age(e.ts)} · {e.lang} · {e.sender}</div>
                <div className="you">{e.body || "(nothing understood)"}</div>
                <div className="line">{e.reply}</div>
              </li>
            ))}
          </ol>
        </details>
      </aside>
    </div>
  );
}
