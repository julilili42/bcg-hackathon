import { escapeHtml } from "./map";
import type { Alternative, Domain, EntityDetail, Feature, Interaction, Report, Stats, StatusRole } from "./types";
import { ROLE_ICON, roleFor } from "./types";

export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const sec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hours = Math.round(min / 60);
  if (hours < 48) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 400) return `${days} d ago`;
  return new Date(iso).getFullYear().toString();
}

export function badge(domain: Domain | undefined, status: string, labelEn?: string): string {
  const role: StatusRole = roleFor(domain, status);
  const en = labelEn ?? domain?.status_labels.en?.[status] ?? status;
  const sw = domain?.status_labels.sw?.[status];
  const swPart = sw && sw !== en ? ` <span class="sw">· ${escapeHtml(sw)}</span>` : "";
  return `<span class="badge role-${role}"><span class="icon" aria-hidden="true">${ROLE_ICON[role]}</span>${escapeHtml(en)}${swPart}</span>`;
}

const CHANNEL_ICON: Record<string, string> = { voice: "☎", sms: "✉", web: "⌨", import: "⇩" };

export function renderDomainTabs(el: HTMLElement, domains: Domain[], active: string, onPick: (id: string) => void): void {
  el.innerHTML = "";
  const ordered = [...domains].sort((a, b) => (a.id === "water" ? -1 : b.id === "water" ? 1 : a.id.localeCompare(b.id)));
  for (const d of ordered) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `tab${d.id === active ? " active" : ""}`;
    b.textContent = d.id === "water" ? "Water points" : d.id === "health" ? "Clinics" : d.entity_type;
    b.addEventListener("click", () => onPick(d.id));
    el.appendChild(b);
  }
}

export function renderStats(el: HTMLElement, stats: Stats | null, domain: Domain | undefined): void {
  if (!stats) {
    el.innerHTML = "";
    return;
  }
  const bad = domain ? domain.bad_statuses.reduce((n, s) => n + (stats.by_status[s] ?? 0), 0) : 0;
  const tiles = [
    { label: domain?.id === "health" ? "Facilities" : "Water points", value: stats.total.toLocaleString(), hint: `${stats.verified} verified` },
    { label: domain?.id === "health" ? "Closed or no stock" : "Not working", value: bad.toLocaleString(), hint: `${stats.disputed} disputed`, role: "serious" as StatusRole },
    { label: "People affected", value: stats.people_affected.toLocaleString(), hint: "served population" },
    { label: "Reports, 24 h", value: stats.reports_24h.toLocaleString(), hint: "phone, SMS, web" },
  ];
  el.innerHTML = tiles
    .map(
      (t) => `<div class="tile${t.role ? ` tile-${t.role}` : ""}">
        <div class="value">${t.value}</div>
        <div class="label">${escapeHtml(t.label)}</div>
        <div class="hint">${escapeHtml(t.hint)}</div>
      </div>`,
    )
    .join("");
}

export function renderLegend(el: HTMLElement, domain: Domain | undefined): void {
  if (!domain) {
    el.innerHTML = "";
    return;
  }
  const statuses = [...domain.good_statuses, ...domain.bad_statuses, "disputed", "unknown"];
  el.innerHTML =
    statuses.map((s) => badge(domain, s)).join("") +
    `<span class="legend-note">faded = last verified by survey only</span>`;
}

export function renderFeed(el: HTMLElement, reports: Report[], domain: Domain | undefined, onPick: (id: string) => void): void {
  if (reports.length === 0) {
    el.innerHTML = `<p class="muted">No live reports yet. Call or text the number, or use the form on a selected point.</p>`;
    return;
  }
  el.innerHTML = reports
    .map(
      (r) => `<article class="item" data-id="${escapeHtml(r.entity_id)}">
        <div class="row">
          <span class="chan" title="${r.channel}">${CHANNEL_ICON[r.channel] ?? "·"}</span>
          <strong>${escapeHtml(r.entity_name ?? r.entity_id)}</strong>
          <time>${timeAgo(r.created_at)}</time>
        </div>
        <div class="row">${badge(domain, r.status_claimed)}${r.raw_text ? `<q>${escapeHtml(r.raw_text)}</q>` : r.note ? `<q>${escapeHtml(r.note)}</q>` : ""}</div>
      </article>`,
    )
    .join("");
  el.querySelectorAll<HTMLElement>(".item").forEach((item) =>
    item.addEventListener("click", () => {
      const id = item.dataset.id;
      if (id) onPick(id);
    }),
  );
}

export function renderInteractions(el: HTMLElement, items: Interaction[]): void {
  if (items.length === 0) {
    el.innerHTML = `<p class="muted">No conversations yet.</p>`;
    return;
  }
  el.innerHTML = items
    .map(
      (i) => `<article class="item talk">
        <div class="row"><span class="chan">${CHANNEL_ICON[i.channel] ?? "·"}</span><span class="muted">${escapeHtml(i.lang ?? "")} · ${escapeHtml(i.intent)} · ${i.latency_ms} ms</span><time>${timeAgo(i.created_at)}</time></div>
        <p class="said">“${escapeHtml(i.body)}”</p>
        <p class="reply">${escapeHtml(i.reply)}</p>
      </article>`,
    )
    .join("");
}

function attributesTable(f: Feature): string {
  const rows = Object.entries(f.properties.attributes)
    .filter(([, v]) => v !== null && v !== "" && v !== undefined)
    .map(([k, v]) => `<tr><th>${escapeHtml(k.replaceAll("_", " "))}</th><td>${escapeHtml(String(v))}</td></tr>`);
  return rows.length ? `<table class="attrs">${rows.join("")}</table>` : "";
}

function alternativesList(alts: Alternative[], domain: Domain | undefined, onPick: (id: string) => void, root: HTMLElement): string {
  if (alts.length === 0) return "";
  const html = `<h3>Nearest working alternative</h3><ol class="alts">${alts
    .map(
      (a) => `<li data-id="${escapeHtml(a.entity_id)}"><strong>${escapeHtml(a.name)}</strong> · ${a.walk_minutes} min walk · ${a.distance_km} km
        ${badge(domain, a.status)}${a.verified ? "" : ' <span class="muted">unverified</span>'}</li>`,
    )
    .join("")}</ol>`;
  queueMicrotask(() =>
    root.querySelectorAll<HTMLElement>(".alts li").forEach((li) =>
      li.addEventListener("click", () => {
        const id = li.dataset.id;
        if (id) onPick(id);
      }),
    ),
  );
  return html;
}

export interface DetailHandlers {
  onPick: (id: string) => void;
  onReport: (entityId: string, status: string, note: string) => Promise<void>;
}

export function renderDetail(el: HTMLElement, detail: EntityDetail | null, domain: Domain | undefined, handlers: DetailHandlers): void {
  if (!detail) {
    el.innerHTML = `<p class="muted">Click a point on the map.</p>`;
    return;
  }
  const p = detail.entity.properties;
  const pct = Math.round(p.confidence * 100);
  const aliases = p.aliases.length ? `<p class="aliases">also known as ${p.aliases.map((a) => `<em>${escapeHtml(a)}</em>`).join(", ")}</p>` : "";
  const statuses = domain ? [...domain.good_statuses, ...domain.bad_statuses] : [];
  el.innerHTML = `
    <h2>${escapeHtml(p.name)}</h2>
    <p class="muted">${[p.adm3, p.adm2, p.adm1].filter(Boolean).map((s) => escapeHtml(String(s))).join(" · ")}${p.served_population ? ` · serves ${p.served_population.toLocaleString()} people` : ""}</p>
    ${aliases}
    <div class="status-line">${badge(domain, p.current_status, p.status_label.en)}
      <span class="muted">${p.verified ? "verified" : "unverified"}${p.last_report_at ? ` · last report ${timeAgo(p.last_report_at)}` : ""}</span></div>
    <div class="confidence" title="confidence ${pct}%"><div class="bar" style="width:${pct}%"></div></div>
    <p class="muted small">confidence ${pct}% · from ${detail.reports.length} report${detail.reports.length === 1 ? "" : "s"}</p>
    ${alternativesList(detail.alternatives, domain, handlers.onPick, el)}
    <h3>Report from the web</h3>
    <form class="report" id="report-form">
      <div class="choices">${statuses
        .map((s) => `<label><input type="radio" name="status" value="${escapeHtml(s)}" required /> ${badge(domain, s)}</label>`)
        .join("")}</div>
      <input type="text" name="note" maxlength="200" placeholder="note (optional)" />
      <button type="submit">Record report</button>
      <span class="form-msg" aria-live="polite"></span>
    </form>
    <h3>Report history</h3>
    <ul class="history">${detail.reports
      .map(
        (r: Report) => `<li><span class="chan">${CHANNEL_ICON[r.channel] ?? "·"}</span> ${badge(domain, r.status_claimed)}
          <span class="muted">${r.channel} · ${timeAgo(r.created_at)}${r.raw_text ? ` · “${escapeHtml(r.raw_text)}”` : ""}</span></li>`,
      )
      .join("")}</ul>
    ${attributesTable(detail.entity)}
  `;
  const form = el.querySelector<HTMLFormElement>("#report-form");
  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const data = new FormData(form);
    const status = String(data.get("status") ?? "");
    const note = String(data.get("note") ?? "");
    const msg = form.querySelector<HTMLElement>(".form-msg");
    if (!status) return;
    try {
      form.querySelector<HTMLButtonElement>("button")!.disabled = true;
      await handlers.onReport(p.id, status, note);
      if (msg) msg.textContent = "Recorded.";
    } catch (err) {
      if (msg) msg.textContent = err instanceof Error ? err.message : "failed";
      form.querySelector<HTMLButtonElement>("button")!.disabled = false;
    }
  });
}
