import { api } from "./api";
import { EntityMap } from "./map";
import { DemoPhone } from "./phone";
import { loadSettings, renderSettings } from "./settings";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import type { Domain, EntityDetail, FeatureCollection, Interaction, Report, Stats } from "./types";
import { renderDetail, renderDomainTabs, renderFeed, renderInteractions, renderLegend, renderStats } from "./ui";

const POLL_MS = 5000;
const FLASH_MS = 9000;

interface State {
  domains: Domain[];
  domainId: string;
  features: FeatureCollection;
  stats: Stats | null;
  reports: Report[];
  interactions: Interaction[];
  selectedId: string | null;
  detail: EntityDetail | null;
  lastStatus: Map<string, string>;
  flash: Map<string, number>;
}

const state: State = {
  domains: [],
  domainId: new URLSearchParams(location.search).get("domain") ?? "water",
  features: { type: "FeatureCollection", features: [] },
  stats: null,
  reports: [],
  interactions: [],
  selectedId: null,
  detail: null,
  lastStatus: new Map(),
  flash: new Map(),
};

const $ = <T extends HTMLElement>(sel: string): T => {
  const el = document.querySelector<T>(sel);
  if (!el) throw new Error(`missing ${sel}`);
  return el;
};

const els = {
  tabs: $("#domain-tabs"),
  stats: $("#stats"),
  legend: $("#legend"),
  feed: $("#panel-feed"),
  detail: $("#panel-detail"),
  talk: $("#panel-talk"),
  live: $("#live"),
};

function createMap(): EntityMap | null {
  try {
    return new EntityMap("map", { onSelect: (id) => void select(id) });
  } catch (err) {
    // No WebGL (old projector laptop, headless browser): the sidebar, feed and phone still work.
    console.error("map unavailable", err);
    $("#map").classList.add("map-unavailable");
    return null;
  }
}

const map = createMap();
const settings = loadSettings();
let demoPhoneAvailable = false;
let phone: DemoPhone | null = null;

function applySettings(): void {
  phone?.setVisible(demoPhoneAvailable && settings.showPhone);
}

function domain(): Domain | undefined {
  return state.domains.find((d) => d.id === state.domainId);
}

function showPanel(name: string): void {
  document.querySelectorAll<HTMLElement>(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  document.querySelectorAll<HTMLElement>("[data-panel]").forEach((b) => b.classList.toggle("active", b.dataset.panel === name));
}

async function select(id: string): Promise<void> {
  state.selectedId = id;
  try {
    state.detail = await api.entity(id);
    const coords = state.detail.entity.geometry.coordinates;
    void map?.flyTo(coords);
    renderDetail(els.detail, state.detail, domain(), { onPick: (pid) => void select(pid), onReport: submitReport });
    showPanel("detail");
    await map?.setData(state.features, domain(), activeFlash(), state.selectedId);
  } catch (err) {
    console.error(err);
  }
}

async function submitReport(entityId: string, status: string, note: string): Promise<void> {
  await api.createReport({ entity_id: entityId, status, note: note || undefined, lang: "en" });
  await refresh();
  if (state.selectedId) await select(state.selectedId);
}

function activeFlash(): Set<string> {
  const now = Date.now();
  for (const [id, until] of state.flash) if (until < now) state.flash.delete(id);
  return new Set(state.flash.keys());
}

async function refresh(): Promise<void> {
  const d = state.domainId;
  try {
    const [features, stats, reports, interactions] = await Promise.all([
      api.entities(d),
      api.stats(d),
      api.reports(d, 30),
      api.interactions(30),
    ]);
    if (state.domainId !== d) return;
    const now = Date.now();
    for (const f of features.features) {
      const prev = state.lastStatus.get(f.id);
      if (prev !== undefined && prev !== f.properties.current_status) state.flash.set(f.id, now + FLASH_MS);
      state.lastStatus.set(f.id, f.properties.current_status);
    }
    state.features = features;
    state.stats = stats;
    state.reports = reports;
    state.interactions = interactions;
    renderStats(els.stats, stats, domain());
    renderLegend(els.legend, domain());
    renderFeed(els.feed, reports, domain(), (id) => void select(id));
    renderInteractions(els.talk, interactions);
    await map?.setData(features, domain(), activeFlash(), state.selectedId);
    els.live.classList.remove("offline");
  } catch (err) {
    els.live.classList.add("offline");
    console.error(err);
  }
}

async function switchDomain(id: string): Promise<void> {
  if (id === state.domainId) return;
  state.domainId = id;
  state.selectedId = null;
  state.detail = null;
  state.lastStatus.clear();
  state.flash.clear();
  history.replaceState(null, "", `?domain=${encodeURIComponent(id)}`);
  renderDomainTabs(els.tabs, state.domains, id, (pick) => void switchDomain(pick));
  renderDetail(els.detail, null, domain(), { onPick: (pid) => void select(pid), onReport: submitReport });
  map?.refit();
  showPanel("feed");
  await refresh();
}

function setupSettings(): void {
  const btn = $("#settings-btn");
  const panel = $("#settings-panel");
  btn.addEventListener("click", () => {
    const open = panel.hidden;
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) renderSettings(panel, settings, demoPhoneAvailable, applySettings);
  });
}

async function boot(): Promise<void> {
  document.querySelectorAll<HTMLElement>("[data-panel]").forEach((b) =>
    b.addEventListener("click", () => showPanel(b.dataset.panel ?? "feed")),
  );
  setupSettings();
  try {
    const [domains, health] = await Promise.all([api.domains(), api.health()]);
    state.domains = domains;
    demoPhoneAvailable = health.demo_phone;
  } catch (err) {
    console.error(err);
  }
  phone = new DemoPhone($("#map"), settings, () => void refresh());
  applySettings();
  if (!state.domains.some((d) => d.id === state.domainId)) state.domainId = state.domains[0]?.id ?? "water";
  renderDomainTabs(els.tabs, state.domains, state.domainId, (id) => void switchDomain(id));
  await refresh();
  setInterval(() => void refresh(), POLL_MS);
  setInterval(() => void map?.setData(state.features, domain(), activeFlash(), state.selectedId), 3000);
}

void boot();
