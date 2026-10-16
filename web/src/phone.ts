/** A Nokia-3310-style virtual phone for demos. Talks to /api/sim/* exactly like Twilio would. */

import { escapeHtml } from "./map";
import { type Settings, saveSettings } from "./settings";
import layoutJson from "./phone-layout.json";
import { type GatherSpec, parseTwiml, type Utterance } from "./twiml";

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
interface PhotoLayout {
  aspect: number;
  lcd: Box;
  lcdColor: string;
  keys: ({ key: string } & Box)[];
}
const PHOTO: PhotoLayout = layoutJson as PhotoLayout;
const PHOTO_SRC = "/phone.webp";
const SVG_SCREEN = { x: 25, y: 27.9, w: 49.3, h: 20.4 };

export const CALLERS = ["+15005550006", "+15005550007", "+15005550008"]; // Twilio magic test numbers

interface Line {
  who: "caller" | "reach" | "info";
  text: string;
}

interface RecognitionResultEvent extends Event {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: Event) => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Keypad geometry (viewBox 280×560), measured from a 3310: left/right columns, middle column 8px lower. */
const KEYS: { key: string; x: number; y: number; letters?: string; accent?: string }[] = [
  { key: "1", x: 82, y: 382, accent: "oo" },
  { key: "2", x: 140, y: 391, letters: "abc" },
  { key: "3", x: 198, y: 382, letters: "def" },
  { key: "4", x: 82, y: 424, letters: "ghi" },
  { key: "5", x: 140, y: 433, letters: "jkl" },
  { key: "6", x: 198, y: 424, letters: "mno" },
  { key: "7", x: 82, y: 466, letters: "pqrs" },
  { key: "8", x: 140, y: 475, letters: "tuv" },
  { key: "9", x: 198, y: 466, letters: "wxyz" },
  { key: "*", x: 82, y: 508, accent: "+" },
  { key: "0", x: 140, y: 517, accent: "⎵" },
  { key: "#", x: 198, y: 508, accent: "⌂" },
];

function keySvg(k: { key: string; x: number; y: number; letters?: string; accent?: string }): string {
  const label = k.key;
  const sub = k.letters
    ? `<text x="${k.x + 4}" y="${k.y + 5}" class="k-letters">${k.letters}</text>`
    : k.accent
      ? `<text x="${k.x + 6}" y="${k.y + 5}" class="k-accent">${k.accent}</text>`
      : "";
  return `
  <g class="key" data-key="${label}" role="button" tabindex="0" aria-label="${label}">
    <rect class="cap" x="${k.x - 31}" y="${k.y - 14}" width="62" height="28" rx="14"/>
    <rect class="cap-hi" x="${k.x - 27}" y="${k.y - 12}" width="54" height="10" rx="5"/>
    <text x="${k.x - 17}" y="${k.y + 5}" class="k-num">${label}</text>
    ${sub}
  </g>`;
}

const SVG_BODY = `
<svg class="phone-art" viewBox="0 0 280 560" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="ph-shell" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#1b1f2a"/><stop offset="0.5" stop-color="#2d3240"/><stop offset="1" stop-color="#171a24"/>
    </linearGradient>
    <linearGradient id="ph-face" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#d7d8da"/><stop offset="0.6" stop-color="#b9bbc0"/><stop offset="1" stop-color="#a3a6ad"/>
    </linearGradient>
    <linearGradient id="ph-cap" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#eceef0"/><stop offset="1" stop-color="#aeb1b8"/>
    </linearGradient>
    <linearGradient id="ph-lcd" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#b3bf9f"/><stop offset="1" stop-color="#9eab8c"/>
    </linearGradient>
    <radialGradient id="ph-sheen" cx="0.35" cy="0.2" r="0.9">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.35"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <g class="art">
    <!-- body: wide top, waist around the middle, rounded bottom -->
    <path d="M46 52 C46 22 62 10 92 10 L188 10 C218 10 234 22 234 52 C238 150 228 250 224 330 C221 410 230 460 231 500 C232 538 206 552 140 552 C74 552 48 538 49 500 C50 460 59 410 56 330 C52 250 42 150 46 52 Z" fill="url(#ph-shell)"/>
    <path d="M46 52 C46 22 62 10 92 10 L188 10 C218 10 234 22 234 52 C238 150 228 250 224 330 C221 410 230 460 231 500 C232 538 206 552 140 552 C74 552 48 538 49 500 C50 460 59 410 56 330 C52 250 42 150 46 52 Z" fill="url(#ph-sheen)"/>
    <!-- silver faceplate -->
    <path d="M60 58 C60 34 72 24 95 24 L185 24 C208 24 220 34 220 58 C224 150 218 250 215 330 L215 350 C189 352 165 304 140 304 C115 304 91 352 65 350 L65 330 C62 250 56 150 60 58 Z" fill="url(#ph-face)" stroke="#111419" stroke-width="1.2"/>
    <!-- speaker holes -->
    <g fill="#141720">
      <circle cx="140" cy="32" r="3.4"/><circle cx="140" cy="46" r="3.4"/><circle cx="140" cy="60" r="3.4"/>
      <circle cx="140" cy="74" r="3.4"/><circle cx="140" cy="88" r="3.4"/>
    </g>
    <!-- label in the logo spot -->
    <rect x="110" y="108" width="60" height="17" rx="2" fill="#20242f"/>
    <text x="140" y="121" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="11" font-weight="800" fill="#e6e7ea" letter-spacing="2.2">REACH</text>
    <!-- screen bezel and LCD -->
    <rect x="64" y="150" width="150" height="126" rx="7" fill="#1a1d26"/>
    <rect x="66" y="152" width="146" height="122" rx="6" fill="#2a2e3a"/>
    <rect x="70" y="156" width="138" height="114" rx="3" fill="url(#ph-lcd)"/>
  </g>
  <g class="keys">
    <!-- left soft key: C -->
    <g class="key soft" data-key="clear" role="button" tabindex="0" aria-label="clear or end" transform="rotate(-11 86 329)">
      <rect class="cap" x="62" y="309" width="48" height="40" rx="12"/>
      <text x="86" y="336" text-anchor="middle" class="k-soft">C</text>
    </g>
    <!-- right soft key: arrow -->
    <g class="key soft" data-key="mode" role="button" tabindex="0" aria-label="switch call or sms" transform="rotate(11 194 329)">
      <rect class="cap" x="170" y="309" width="48" height="40" rx="12"/>
      <text x="194" y="336" text-anchor="middle" class="k-soft">↵</text>
    </g>
    <!-- centre select key -->
    <g class="key select" data-key="select" role="button" tabindex="0" aria-label="call or send">
      <rect class="cap" x="102" y="280" width="76" height="20" rx="10"/>
      <rect x="122" y="289" width="36" height="3" rx="1.5" fill="#3fae57"/>
    </g>
    ${KEYS.map(keySvg).join("")}
  </g>
</svg>`;

export class DemoPhone {
  private root: HTMLElement;
  private mode: "call" | "sms" = "call";
  private inCall = false;
  private busy = false;
  private gather: GatherSpec | null = null;
  private lines: Line[] = [];
  private recognition: Recognition | null = null;
  private listening = false;
  private open = false;
  private closeTimer: number | null = null;

  constructor(
    container: HTMLElement,
    private settings: Settings,
    private onActivity: () => void,
  ) {
    this.root = document.createElement("div");
    this.root.className = "phone";
    this.root.dataset.open = "false";
    container.appendChild(this.root);
    this.render();
    this.root.addEventListener("mouseenter", () => this.setOpen(true));
    this.root.addEventListener("click", (ev) => {
      if (!this.open) {
        ev.preventDefault();
        this.setOpen(true);
      }
    });
    if (new URLSearchParams(location.search).get("phone") === "open") this.setOpen(true);
  }

  setVisible(visible: boolean): void {
    this.root.hidden = !visible;
  }

  setOpen(open: boolean): void {
    this.open = open;
    this.root.dataset.open = String(open);
    if (open) this.root.querySelector<HTMLInputElement>(".screen-input input")?.focus();
  }

  private caller(): string {
    return CALLERS[this.settings.caller] ?? CALLERS[0] ?? "+15005550006";
  }

  private screenHtml(micSupported: boolean): string {
    return `
        <div class="phone-screen" aria-live="polite">
          <div class="screen-top"><span class="screen-mode"></span><span class="screen-lang"></span></div>
          <div class="screen-lines"></div>
          <form class="screen-input">
            <input type="text" autocomplete="off" placeholder="" />
            <button type="button" class="mic" title="speak (browser speech recognition)" ${micSupported ? "" : "hidden"}>🎙</button>
          </form>
          <div class="screen-soft"><span class="soft-left"></span><span class="soft-mid">▬</span><span class="soft-right"></span></div>
        </div>`;
  }

  private render(): void {
    this.root.innerHTML = `
      <div class="phone-hint">Demo phone · hover to open</div>
      <div class="phone-toolbar">
        <span class="group" role="group" aria-label="mode">
          <button type="button" data-mode="call" class="active">Call</button>
          <button type="button" data-mode="sms">SMS</button>
        </span>
        <span class="group" role="group" aria-label="call language" title="language of the greeting; the caller can still press 2">
          <button type="button" data-lang="sw">Kiswahili</button>
          <button type="button" data-lang="en">English</button>
        </span>
        <select class="caller" title="which phone is this">
          ${CALLERS.map((c, i) => `<option value="${i}">Phone ${i + 1}</option>`).join("")}
        </select>
        <button type="button" class="call-btn green" title="start a call">📞 Call</button>
        <button type="button" class="phone-close" title="close">✕</button>
      </div>
      <div class="phone-body"></div>`;
    const callerSel = this.root.querySelector<HTMLSelectElement>(".caller")!;
    callerSel.value = String(this.settings.caller);
    callerSel.addEventListener("change", () => {
      this.settings.caller = Number(callerSel.value);
      this.info(`Now using Phone ${this.settings.caller + 1}`);
    });
    this.root.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach((b) =>
      b.addEventListener("click", () => this.setMode(b.dataset.mode === "sms" ? "sms" : "call")),
    );
    this.root.querySelectorAll<HTMLButtonElement>("[data-lang]").forEach((b) =>
      b.addEventListener("click", () => {
        this.settings.callLang = b.dataset.lang === "en" ? "en" : "sw";
        saveSettings(this.settings);
        if (!this.inCall) this.info(this.settings.callLang === "en" ? "Next call starts in English." : "Simu ijayo itaanza kwa Kiswahili.");
        this.paintScreen();
      }),
    );
    this.root.querySelector<HTMLButtonElement>(".call-btn")!.addEventListener("click", () => {
      if (this.inCall) this.endCall(true);
      else void this.press("call");
    });
    this.root.querySelector<HTMLButtonElement>(".phone-close")!.addEventListener("click", () => this.setOpen(false));
    this.lines = [{ who: "info", text: "Press the middle key or 📞 to call Reach, ↵ for SMS." }];
    this.applySkin("photo");
  }

  /** Photo skin: the real handset with transparent hit areas. SVG skin: drawn fallback when the image fails. */
  private applySkin(skin: "photo" | "svg"): void {
    const body = this.root.querySelector<HTMLElement>(".phone-body")!;
    const micSupported = recognitionCtor() !== null;
    this.root.dataset.skin = skin;
    const width = 240;
    if (skin === "photo") {
      const height = Math.round(width * PHOTO.aspect);
      this.root.style.setProperty("--phone-w", `${width}px`);
      this.root.style.setProperty("--phone-h", `${height}px`);
      this.setScreenVars(PHOTO.lcd, PHOTO.lcdColor);
      const hits = PHOTO.keys
        .map(
          (k) =>
            `<button type="button" class="hit hit-${k.key === "*" ? "star" : k.key === "#" ? "hash" : k.key}" data-key="${k.key}" aria-label="${k.key}"
              style="left:${k.x}%;top:${k.y}%;width:${k.w}%;height:${k.h}%"></button>`,
        )
        .join("");
      body.innerHTML = `<img class="phone-img" src="${PHOTO_SRC}" alt="" draggable="false" />${hits}${this.screenHtml(micSupported)}`;
      const img = body.querySelector<HTMLImageElement>(".phone-img")!;
      img.addEventListener("error", () => this.applySkin("svg"));
    } else {
      this.root.style.setProperty("--phone-w", `${width}px`);
      this.root.style.setProperty("--phone-h", `${width * 2}px`);
      this.setScreenVars(SVG_SCREEN, "#a8b596");
      body.innerHTML = `${SVG_BODY}${this.screenHtml(micSupported)}`;
    }
    this.bindBody();
    this.paintScreen();
  }

  private setScreenVars(box: Box, color: string): void {
    this.root.style.setProperty("--screen-left", `${box.x}%`);
    this.root.style.setProperty("--screen-top", `${box.y}%`);
    this.root.style.setProperty("--screen-w", `${box.w}%`);
    this.root.style.setProperty("--screen-h", `${box.h}%`);
    this.root.style.setProperty("--lcd", color);
  }

  private bindBody(): void {
    this.root.querySelectorAll<HTMLElement>(".phone-body [data-key]").forEach((el) => {
      el.addEventListener("click", () => void this.press(el.dataset.key ?? ""));
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          void this.press(el.dataset.key ?? "");
        }
      });
    });
    const form = this.root.querySelector<HTMLFormElement>(".screen-input")!;
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      void this.submitText();
    });
    form.querySelector<HTMLInputElement>("input")!.addEventListener("input", () => this.paintScreen());
    this.root.querySelector<HTMLButtonElement>(".mic")!.addEventListener("click", () => this.toggleMic());
  }

  private setMode(mode: "call" | "sms"): void {
    if (this.inCall) this.endCall(false);
    this.mode = mode;
    this.root.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    this.lines = [
      mode === "call"
        ? { who: "info", text: "Press the middle key to call Reach." }
        : { who: "info", text: "Type a message, press the middle key. Try: Shule imeharibika" },
    ];
    this.paintScreen();
  }

  private info(text: string): void {
    this.lines.push({ who: "info", text });
    this.paintScreen();
  }

  private inputEl(): HTMLInputElement {
    return this.root.querySelector<HTMLInputElement>(".screen-input input")!;
  }

  private paintScreen(): void {
    const linesEl = this.root.querySelector<HTMLElement>(".screen-lines")!;
    linesEl.innerHTML = this.lines
      .slice(-8)
      .map((l) => `<div class="line ${l.who}">${l.who === "caller" ? "› " : l.who === "reach" ? "" : "· "}${escapeHtml(l.text)}</div>`)
      .join("");
    linesEl.scrollTop = linesEl.scrollHeight;
    const modeEl = this.root.querySelector<HTMLElement>(".screen-mode")!;
    modeEl.textContent =
      this.mode === "sms"
        ? `SMS · Phone ${this.settings.caller + 1}`
        : this.inCall
          ? this.busy
            ? "Connecting…"
            : this.listening
              ? "Listening…"
              : "In call"
          : `Phone ${this.settings.caller + 1}`;
    this.root.querySelector<HTMLElement>(".screen-lang")!.textContent = this.gather ? this.gather.language : "";
    const input = this.inputEl();
    const canType = this.mode === "sms" || (this.inCall && this.gather !== null && !this.busy);
    input.disabled = !canType;
    input.placeholder = this.mode === "sms" ? "type an SMS" : this.gather ? "type what the caller says, or press a key" : "";
    const mic = this.root.querySelector<HTMLButtonElement>(".mic")!;
    mic.disabled = !canType || this.mode === "sms";
    mic.classList.toggle("listening", this.listening);
    const hasText = input.value.trim().length > 0;
    this.root.querySelectorAll<HTMLButtonElement>("[data-lang]").forEach((b) => b.classList.toggle("active", b.dataset.lang === this.settings.callLang));
    const callBtn = this.root.querySelector<HTMLButtonElement>(".call-btn");
    if (callBtn) {
      callBtn.textContent = this.inCall ? "⏏ Hang up" : "📞 Call";
      callBtn.title = this.inCall ? "end the call" : "start a call";
      callBtn.classList.toggle("green", !this.inCall);
      callBtn.classList.toggle("red", this.inCall);
    }
    this.root.querySelector<HTMLElement>(".soft-left")!.textContent = this.inCall ? "End" : hasText ? "Clear" : "Close";
    this.root.querySelector<HTMLElement>(".soft-mid")!.textContent =
      this.mode === "sms" ? "Send" : this.inCall ? (this.gather ? "Send" : "…") : "Call";
    this.root.querySelector<HTMLElement>(".soft-right")!.textContent = this.mode === "call" ? "SMS" : "Call";
  }

  // ------------------------------------------------------------------ keys
  private async press(key: string): Promise<void> {
    if (key === "call") {
      if (this.mode === "sms") this.setMode("call");
      if (!this.inCall) await this.startCall();
      return;
    }
    if (key === "select") {
      if (this.mode === "sms" || (this.inCall && this.gather)) {
        await this.submitText();
      } else if (!this.inCall) {
        await this.startCall();
      }
      return;
    }
    if (key === "clear") {
      if (this.inCall) this.endCall(true);
      else if (this.inputEl().value) {
        this.inputEl().value = "";
        this.paintScreen();
      } else this.setOpen(false);
      return;
    }
    if (key === "mode") {
      this.setMode(this.mode === "call" ? "sms" : "call");
      return;
    }
    if (this.inCall && this.gather && !this.busy && this.gather.input.includes("dtmf")) {
      this.lines.push({ who: "caller", text: `[key ${key}]` });
      await this.post(this.gather.action, { Digits: key, SpeechResult: "" });
    } else if (this.mode === "sms") {
      this.inputEl().value += key;
      this.paintScreen();
    }
  }

  private async startCall(): Promise<void> {
    this.inCall = true;
    this.gather = null;
    const lang = this.settings.callLang;
    this.lines = [{ who: "info", text: `Calling Reach from Phone ${this.settings.caller + 1} (${lang === "en" ? "English" : "Kiswahili"})…` }];
    this.paintScreen();
    await this.post(`/api/sim/voice?lang=${lang}`, {});
  }

  private endCall(sayIt: boolean): void {
    this.inCall = false;
    this.gather = null;
    this.stopMic();
    if (sayIt) this.lines.push({ who: "info", text: "Call ended." });
    this.paintScreen();
    if (sayIt) {
      if (this.closeTimer) window.clearTimeout(this.closeTimer);
      this.closeTimer = window.setTimeout(() => this.setOpen(false), 1500);
    }
  }

  private async submitText(): Promise<void> {
    const input = this.inputEl();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    if (this.mode === "sms") {
      await this.sendSms(text);
      return;
    }
    if (this.inCall && this.gather && !this.busy) {
      this.lines.push({ who: "caller", text });
      await this.post(this.gather.action, { SpeechResult: text, Digits: "" });
    }
  }

  private async post(url: string, fields: Record<string, string>): Promise<void> {
    this.busy = true;
    this.paintScreen();
    try {
      const body = new URLSearchParams({ From: this.caller(), CallSid: "SIM" + this.settings.caller, ...fields });
      const res = await fetch(url, { method: "POST", body, headers: { Accept: "text/xml" } });
      if (!res.ok) throw new Error(`${res.status} from ${url}`);
      const result = parseTwiml(await res.text());
      for (const u of result.utterances) this.lines.push({ who: "reach", text: u.kind === "say" ? u.text : "🔊 (audio reply)" });
      this.gather = result.gather;
      this.paintScreen();
      void this.speak(result.utterances, result.gather?.language ?? "en-US");
      this.onActivity();
      if (result.redirect) {
        await this.post(result.redirect, {});
        return;
      }
      if (result.hangup) {
        window.setTimeout(() => this.endCall(true), 600);
      }
    } catch (err) {
      this.lines.push({ who: "info", text: err instanceof Error ? err.message : "call failed" });
      this.gather = null;
    } finally {
      this.busy = false;
      this.paintScreen();
    }
  }

  private async sendSms(text: string): Promise<void> {
    this.lines.push({ who: "caller", text });
    this.busy = true;
    this.paintScreen();
    try {
      const body = new URLSearchParams({ From: this.caller(), Body: text });
      const res = await fetch("/api/sim/sms", { method: "POST", body, headers: { Accept: "text/xml" } });
      if (!res.ok) throw new Error(`${res.status}`);
      const result = parseTwiml(await res.text());
      for (const m of result.messages) this.lines.push({ who: "reach", text: m });
      this.onActivity();
    } catch (err) {
      this.lines.push({ who: "info", text: err instanceof Error ? err.message : "sms failed" });
    } finally {
      this.busy = false;
      this.paintScreen();
    }
  }

  // ---------------------------------------------------------------- speech
  private async speak(utterances: Utterance[], language: string): Promise<void> {
    for (const u of utterances) {
      if (u.kind === "play") {
        await new Promise<void>((resolve) => {
          const audio = new Audio(u.url);
          audio.onended = () => resolve();
          audio.onerror = () => resolve();
          void audio.play().catch(() => resolve());
        });
      } else if (this.settings.speak && "speechSynthesis" in window) {
        await new Promise<void>((resolve) => {
          const utter = new SpeechSynthesisUtterance(u.text);
          utter.lang = language;
          const voices = speechSynthesis.getVoices();
          const match = voices.find((v) => v.lang.toLowerCase().startsWith(language.slice(0, 2).toLowerCase()));
          if (match) utter.voice = match;
          utter.onend = () => resolve();
          utter.onerror = () => resolve();
          speechSynthesis.speak(utter);
        });
      }
    }
  }

  private toggleMic(): void {
    if (this.listening) {
      this.stopMic();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor || !this.gather) return;
    const rec = new Ctor();
    rec.lang = this.gather.language;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const transcript = e.results[0]?.[0]?.transcript?.trim() ?? "";
      this.stopMic();
      if (transcript && this.gather) {
        this.lines.push({ who: "caller", text: transcript });
        void this.post(this.gather.action, { SpeechResult: transcript, Digits: "" });
      }
    };
    rec.onend = () => this.stopMic();
    rec.onerror = () => this.stopMic();
    this.recognition = rec;
    this.listening = true;
    this.paintScreen();
    rec.start();
  }

  private stopMic(): void {
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {
        /* already stopped */
      }
    }
    this.recognition = null;
    this.listening = false;
    this.paintScreen();
  }
}
