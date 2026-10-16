/** Per-browser conveniences. localStorage can be empty or throw; the page must work without it. */

export interface Settings {
  showPhone: boolean;
  speak: boolean;
  caller: number;
  callLang: "sw" | "en";
}

const KEY = "reach.settings";
const DEFAULTS: Settings = { showPhone: true, speak: true, caller: 0, callLang: "sw" };

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveSettings(settings: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    /* private window or blocked storage: keep in memory only */
  }
}

export function renderSettings(panel: HTMLElement, settings: Settings, demoPhoneAvailable: boolean, onChange: () => void): void {
  panel.innerHTML = `
    <h3>Settings</h3>
    <label class="setting"><input type="checkbox" name="showPhone" ${settings.showPhone ? "checked" : ""} ${demoPhoneAvailable ? "" : "disabled"} />
      Show demo phone${demoPhoneAvailable ? "" : ' <span class="muted">(DEMO_PHONE=0 on the server)</span>'}</label>
    <label class="setting"><input type="checkbox" name="speak" ${settings.speak ? "checked" : ""} />
      Speak replies aloud (browser voice when no audio is returned)</label>
    <p class="muted small">Stored in this browser only.</p>
  `;
  panel.querySelectorAll<HTMLInputElement>("input[type=checkbox]").forEach((box) =>
    box.addEventListener("change", () => {
      if (box.name === "showPhone") settings.showPhone = box.checked;
      if (box.name === "speak") settings.speak = box.checked;
      saveSettings(settings);
      onChange();
    }),
  );
}
