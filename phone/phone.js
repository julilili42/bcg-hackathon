// Browser phone. Real call through Twilio Voice SDK -> TwiML App -> /api/voice. Keys send DTMF during a call.
const $ = (id) => document.getElementById(id);
const screen = $("screen"), status = $("status"), softL = $("soft-left"), softR = $("soft-right"), log = $("log");

let device = null, call = null, number = "", dialed = "", startedAt = 0, timers = {};

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const clock = () => { $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
clock(); setInterval(clock, 15000);

function show(lines, { big = false } = {}) {
  screen.innerHTML = "";
  for (const [i, l] of [].concat(lines).entries()) {
    const d = document.createElement("div");
    d.textContent = l;
    if (big && i === 0) d.className = "big";
    if (l.startsWith("·")) d.className = "dim";
    screen.appendChild(d);
  }
}

function idle(msg) {
  status.textContent = "ready";
  softL.textContent = "Call"; softR.textContent = "Clear";
  $("btn-call").disabled = false; $("btn-end").disabled = true;
  show(msg || [dialed || number, "", "· green key: call the line", "· during a call: 2 = English"], { big: true });
}

async function init() {
  const r = await fetch("/api/phone/token");
  if (!r.ok) { status.textContent = "no setup"; show(["Setup missing", "", await r.text()]); return; }
  const data = await r.json();
  number = data.number || "+1 865 459 8142";
  device = new Twilio.Device(data.token, { codecPreferences: ["opus", "pcmu"], closeProtection: true });
  device.on("error", (e) => { status.textContent = "error"; show(["Error", "", e.message]); });
  device.on("tokenWillExpire", async () => device.updateToken((await (await fetch("/api/phone/token")).json()).token));
  idle();
}

async function dial() {
  if (!device || call) return;
  status.textContent = "calling"; softL.textContent = ""; softR.textContent = "End";
  $("btn-call").disabled = true; $("btn-end").disabled = false;
  show([number, "", "Calling…", "· allow the microphone"], { big: true });
  try {
    call = await device.connect({ params: { To: number } });
  } catch (e) { call = null; idle(["Call failed", "", e.message]); return; }
  call.on("accept", () => {
    startedAt = Date.now(); status.textContent = "in call";
    timers.tick = setInterval(() => show([number, "", fmt(Math.round((Date.now() - startedAt) / 1000)), "· speak after the greeting", "· press 2 for English"], { big: true }), 1000);
    timers.poll = setInterval(refreshLog, 1500);
  });
  call.on("disconnect", hangup);
  call.on("cancel", hangup);
  call.on("reject", hangup);
}

function hangup() {
  if (call) { try { call.disconnect(); } catch (_) {} }
  call = null;
  clearInterval(timers.tick); clearInterval(timers.poll);
  setTimeout(refreshLog, 1500); setTimeout(refreshLog, 4000);
  idle(["Call ended", "", "· see the live panel", "· green key: call again"]);
}

function key(d) {
  if (call) { call.sendDigits(d); show([number, "", fmt(Math.round((Date.now() - startedAt) / 1000)), `· sent ${d}`], { big: true }); return; }
  dialed += d; show([dialed, "", "· this phone only reaches the line", "· green key to call"], { big: true });
}

async function refreshLog() {
  const d = await (await fetch("/api/events")).json();
  const mine = d.events.filter((e) => e.channel === "voice").slice(0, 6);
  log.innerHTML = "";
  if (!mine.length) { log.innerHTML = '<li class="empty">No calls yet.</li>'; return; }
  for (const e of mine) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="who">${e.ts.slice(11, 19)} · ${e.lang}</div><div class="you">${esc(e.body) || "(nothing understood)"}</div><div class="line">${esc(e.reply)}</div>`;
    log.appendChild(li);
  }
}
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

$("btn-call").onclick = dial;
$("btn-end").onclick = () => { if (call) hangup(); else { dialed = ""; idle(); } };
$("btn-nav").onclick = refreshLog;
for (const b of document.querySelectorAll("[data-digit]")) b.onclick = () => key(b.dataset.digit);
document.addEventListener("keydown", (ev) => {
  if (/^[0-9*#]$/.test(ev.key)) { key(ev.key); const b = document.querySelector(`[data-digit="${ev.key}"]`); b.classList.add("pressed"); setTimeout(() => b.classList.remove("pressed"), 120); }
  else if (ev.key === "Enter") dial();
  else if (ev.key === "Escape") $("btn-end").click();
});

status.textContent = "starting"; show(["Reach Line", "", "· loading…"], { big: true });
init().catch((e) => show(["Error", "", e.message]));
refreshLog();
