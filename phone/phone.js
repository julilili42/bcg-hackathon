// Real Nokia 3310 photo as chassis; a real call through Twilio Voice SDK -> TwiML App -> /api/voice.
// Navi key = call, C = hang up / clear, digits = DTMF during a call (2 = English). Right side: the live database.
const $ = (id) => document.getElementById(id);
const lcd = $("lcd"), main = $("lcd-main"), soft = $("lcd-soft"), stat = $("lcd-status"), navi = $("key-navi"), log = $("log"), wp = $("wp");

let device = null, call = null, number = "", dialed = "", startedAt = 0, timers = {}, lastStatus = {};
const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const pretty = (n) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3");
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function show(lines, status, softkey) {
  main.innerHTML = "";
  for (const l of lines) {
    const d = document.createElement("div");
    const [cls, text] = typeof l === "string" ? ["", l] : l;
    d.className = cls; d.textContent = text; main.appendChild(d);
  }
  if (status !== undefined) stat.textContent = status;
  if (softkey !== undefined) soft.textContent = softkey;
}
const idle = (lines) => { navi.classList.remove("live"); show(lines || [["big", dialed || pretty(number)], "Reach Line", "Navi = call"], "", "Call"); };

async function init() {
  const r = await fetch("/api/phone/token");
  if (!r.ok) { show(["Setup missing", "run phone/", "setup.py"], "!", ""); addLog("error", "Setup", await r.text()); return; }
  const data = await r.json();
  number = data.number || "+18654598142";
  $("num").textContent = number.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "+1 $1 $2 $3");
  device = new Twilio.Device(data.token, { codecPreferences: ["opus", "pcmu"], closeProtection: true });
  device.on("error", (e) => { show(["Error", e.code ? `code ${e.code}` : "", "see panel"], "!", "Call"); addLog("error", "Twilio", e.message); });
  device.on("tokenWillExpire", async () => device.updateToken((await (await fetch("/api/phone/token")).json()).token));
  lcd.classList.add("on");
  idle();
}

async function dial() {
  if (!device || call) return;
  show([["big", pretty(number)], ["blink", "Calling..."], "allow mic"], "", "End");
  try { call = await device.connect({ params: { To: number } }); }
  catch (e) { call = null; idle(["Call failed", "see panel", "Navi = retry"]); addLog("error", "Call", e.message); return; }
  navi.classList.add("live");
  call.on("accept", () => {
    startedAt = Date.now();
    timers.tick = setInterval(() => show([["big", pretty(number)], fmt(Math.round((Date.now() - startedAt) / 1000)), "speak / 2=EN"], "", "End"), 1000);
  });
  for (const ev of ["disconnect", "cancel", "reject"]) call.on(ev, hangup);
}

function hangup() {
  if (call) { try { call.disconnect(); } catch (_) {} }
  call = null; clearInterval(timers.tick);
  idle(["Call ended", "Navi = call"]);
}

function key(d) {
  if (call) { call.sendDigits(d); show([["big", pretty(number)], fmt(Math.round((Date.now() - startedAt) / 1000)), `sent ${d}`], "", "End"); return; }
  dialed = (dialed + d).slice(-14);
  show([["big", dialed], "only the line", "Navi = call"], "", "Call");
}

function addLog(cls, who, text) {
  const li = document.createElement("li"); li.className = cls;
  li.innerHTML = `<div class="who">${esc(who)}</div><div class="line">${esc(text)}</div>`;
  log.prepend(li);
}

const age = (ts) => {
  const s = Math.max(0, Math.round((Date.now() - new Date(ts.replace(" ", "T") + "Z")) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`;
};

async function refresh() {
  let d;
  try { d = await (await fetch("/api/events")).json(); } catch (_) { return; }
  wp.innerHTML = "";
  for (const w of d.waterpoints) {
    const tr = document.createElement("tr");
    if (lastStatus[w.id] && lastStatus[w.id] !== w.status) tr.className = "changed";
    lastStatus[w.id] = w.status;
    tr.innerHTML = `<td>${esc(w.name)}</td><td>${esc(w.village)}</td><td class="status ${w.status}">${w.status}</td><td class="age">${age(String(w.updated))}</td>`;
    wp.appendChild(tr);
  }
  const calls = d.events.filter((e) => e.channel === "voice").slice(0, 3);
  for (const li of [...log.children]) if (!li.classList.contains("error")) li.remove();
  if (!calls.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = "No calls yet."; log.appendChild(li); }
  for (const e of calls) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="who">${age(e.ts)} · ${e.lang} · ${esc(e.sender)}</div><div class="you">${esc(e.body) || "(nothing understood)"}</div><div class="line">${esc(e.reply)}</div>`;
    log.appendChild(li);
  }
}

navi.onclick = () => (call ? null : dial());
$("key-c").onclick = () => { if (call) hangup(); else { dialed = ""; idle(); } };
$("key-prev").onclick = $("key-next").onclick = refresh;
for (const b of document.querySelectorAll("[data-digit]")) b.onclick = () => key(b.dataset.digit);
document.addEventListener("keydown", (ev) => {
  if (/^[0-9*#]$/.test(ev.key)) { key(ev.key); const b = document.querySelector(`[data-digit="${ev.key}"]`); b.classList.add("pressed"); setTimeout(() => b.classList.remove("pressed"), 120); }
  else if (ev.key === "Enter") dial();
  else if (ev.key === "Escape") $("key-c").click();
});

show([["big", "NOKIA"], "Reach Line", "loading"], "", "");
init().catch((e) => { show(["Error", "see panel"], "!", ""); addLog("error", "Init", e.message); });
refresh(); setInterval(refresh, 2000);
