// Nokia 3310 in the browser, real call through Twilio Voice SDK -> TwiML App -> /api/voice.
// Navi key = call, C = hang up / clear, digits = DTMF during a call (2 = English menu).
const $ = (id) => document.getElementById(id);
const lcd = $("lcd"), main = $("lcd-main"), soft = $("lcd-soft"), stat = $("lcd-status"), navi = $("key-navi"), log = $("log");

let device = null, call = null, number = "", dialed = "", startedAt = 0, timers = {};
const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const pretty = (n) => n.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3");

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

function idle(lines) {
  navi.classList.remove("live");
  show(lines || [["big", dialed || pretty(number)], "Reach Line", "Navi = call"], "", "Call");
}

async function init() {
  const r = await fetch("/api/phone/token");
  if (!r.ok) { show(["Setup missing", "run phone/", "setup.py"], "!", ""); addLog("error", "Setup", await r.text()); return; }
  const data = await r.json();
  number = data.number || "+18654598142";
  device = new Twilio.Device(data.token, { codecPreferences: ["opus", "pcmu"], closeProtection: true });
  device.on("error", (e) => { show(["Error", e.code ? `code ${e.code}` : "", "see panel"], "!", "Call"); addLog("error", "Twilio", e.message); });
  device.on("tokenWillExpire", async () => device.updateToken((await (await fetch("/api/phone/token")).json()).token));
  lcd.classList.add("on");
  idle();
}

async function dial() {
  if (!device || call) return;
  show([["big", pretty(number)], ["blink", "Calling..."], "allow mic"], "", "End");
  try {
    call = await device.connect({ params: { To: number } });
  } catch (e) { call = null; idle(["Call failed", "see panel", "Navi = retry"]); addLog("error", "Call", e.message); return; }
  navi.classList.add("live");
  call.on("accept", () => {
    startedAt = Date.now();
    timers.tick = setInterval(() => show([["big", pretty(number)], fmt(Math.round((Date.now() - startedAt) / 1000)), "speak / 2=EN"], "", "End"), 1000);
    timers.poll = setInterval(refreshLog, 1500);
  });
  for (const ev of ["disconnect", "cancel", "reject"]) call.on(ev, hangup);
}

function hangup() {
  if (call) { try { call.disconnect(); } catch (_) {} }
  call = null;
  clearInterval(timers.tick); clearInterval(timers.poll);
  setTimeout(refreshLog, 1500); setTimeout(refreshLog, 4000);
  idle(["Call ended", "see panel", "Navi = call"]);
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

async function refreshLog() {
  const d = await (await fetch("/api/events")).json();
  const mine = d.events.filter((e) => e.channel === "voice").slice(0, 6);
  for (const li of [...log.children]) if (!li.classList.contains("error")) li.remove();
  if (!mine.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = "No calls yet."; log.appendChild(li); return; }
  for (const e of mine) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="who">${e.ts.slice(11, 19)} · ${e.lang}</div><div class="you">${esc(e.body) || "(nothing understood)"}</div><div class="line">${esc(e.reply)}</div>`;
    log.appendChild(li);
  }
}
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

navi.onclick = () => (call ? null : dial());
$("key-c").onclick = () => { if (call) hangup(); else { dialed = ""; idle(); } };
$("key-prev").onclick = () => log.scrollBy({ top: -120, behavior: "smooth" });
$("key-next").onclick = () => log.scrollBy({ top: 120, behavior: "smooth" });
for (const b of document.querySelectorAll("[data-digit]")) b.onclick = () => key(b.dataset.digit);
document.addEventListener("keydown", (ev) => {
  if (/^[0-9*#]$/.test(ev.key)) { key(ev.key); const b = document.querySelector(`[data-digit="${ev.key}"]`); b.classList.add("pressed"); setTimeout(() => b.classList.remove("pressed"), 120); }
  else if (ev.key === "Enter") dial();
  else if (ev.key === "Escape") $("key-c").click();
});

show([["big", "NOKIA"], "Reach Line", "loading"], "", "");
init().catch((e) => { show(["Error", "see panel"], "!", ""); addLog("error", "Init", e.message); });
refreshLog();
