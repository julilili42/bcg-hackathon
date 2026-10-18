// Leaflet map of the water points, the villages and the messages: every status report is a badge next to its water point,
// every danger on the way a warning triangle on the red route between the village and the water point.
// `focus` = the place a call just named: the map flies there. A water point opens its popup, and when it is down the nearest
// working one is shown as the alternative (same straight-line walk as gateway/graph.py). A village alone shows its two nearest
// water points; a village and a water point show the way between them. Without focus it shows all points. OpenStreetMap tiles.
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { COLOR, HAZARD_LABEL, age, type HazardKind, type LogEvent, type Place, type Status, type Village, type Waterpoint } from "./api";

// Leaflet's flyTo follows a flight path that overshoots the target zoom and comes back when the pan is short, and it
// scales the markers up to 8x on the way. glide() moves zoom and centre monotonically with one ease-in-out and
// redraws the markers every frame, so they keep their size. Uses the same map internals flyTo itself uses.
function glide(m: L.Map, target: L.LatLng, zoom: number, duration = 2.0) {
  const map = m as unknown as { _stop(): void; _moveStart(z: boolean, n: boolean): void; _move(c: L.LatLng, z: number): L.Map & { _moveEnd(z: boolean): void }; _renderer?: { _reset(): void }; _flyToFrame?: number };
  map._stop();
  const z0 = m.getZoom(), c0 = m.project(m.getCenter(), zoom), c1 = m.project(target, zoom);
  // _move at a constant zoom fires no "zoom" event, so the tiles would stay where they were: one place to the next at the
  // same zoom is a plain pan
  if (Math.abs(zoom - z0) < 0.01) { m.panTo(target, { animate: true, duration, easeLinearity: 0.5 }); return; }
  const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const start = performance.now();
  map._moveStart(true, false);
  const frame = () => {
    const t = Math.min(1, (performance.now() - start) / (duration * 1000)), e = ease(t);
    if (t < 1) {
      map._move(m.unproject(c0.add(c1.subtract(c0).multiplyBy(e)), zoom), z0 + (zoom - z0) * e);
      map._renderer?._reset();
      map._flyToFrame = L.Util.requestAnimFrame(frame, m);
    } else {
      map._move(target, zoom)._moveEnd(true);
    }
  };
  frame();
}
const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
const popup = (w: Waterpoint, from?: Waterpoint, km?: number) =>  // one line; the alternative gets a second, small one
  `<b>${esc(w.name)}</b> · ${esc(w.village)}`  // the status is the marker's colour
  + (from === undefined || km === undefined ? "" : `<br><small>~${walkMinutes(km)} min from ${esc(from.name)}</small>`);
const walkMinutes = (km: number) => Math.max(5, 5 * Math.round(km / 4 * 60 / 5));  // like db.walk_minutes: 4 km/h, rounded to 5

const distanceKm = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) => {  // great-circle, like db.distance_km; walking at 4 km/h
  const r = Math.PI / 180, p1 = a.lat * r, p2 = b.lat * r, dp = p2 - p1, dl = (b.lon - a.lon) * r;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
};
export const TRIANGLE = '<svg viewBox="0 0 30 27" width="30" height="27" aria-hidden="true"><path d="M15 2 28.5 25.5h-27z" fill="#d92d20" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M15 10v7" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><circle cx="15" cy="21" r="1.6" fill="#fff"/></svg>';
// one symbol per message; several at one place fan out, so each new one is visible
const GLYPH: Record<Status, string> = { ok: "M6 10.5l3 3 5-6", broken: "M6.5 6.5l7 7M13.5 6.5l-7 7", empty: "M6 10h8" };
export const badge = (status: Status) => `<svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true"><circle cx="10" cy="10" r="8.5" fill="${COLOR[status]}" stroke="#fff" stroke-width="2"/><path d="${GLYPH[status]}" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`;
const said = (e: LogEvent) => `<small class="said">“${esc(e.body)}”</small>`;
const messagePopup = (e: LogEvent) => e.kind === "hazard"  // title, then where and when in one small line, then the words
  ? `<b>${HAZARD_LABEL[e.detail as HazardKind] ?? "Danger"} on the way</b><br><small>${esc(e.village ?? "")} → ${esc(e.point ?? "")} · ${age(e.ts)}</small>${said(e)}`
  : `<b>${esc(e.point ?? "")} · ${esc(e.detail ?? "")}</b><br><small>${e.channel} · ${age(e.ts)}</small>${said(e)}`;
const FAN = [0, 1, -1, 2, -2, 3, -3];  // k-th message at one place: 0 in the middle, then alternately either side
const nearestTo = (v: Village, all: Waterpoint[], n: number) =>
  all.map((w) => ({ w, km: distanceKm(v, w) })).sort((a, b) => a.km - b.km).slice(0, n).map((x) => x.w);

const nearestWorking = (f: Waterpoint, all: Waterpoint[]) => {
  if (f.status === "ok") return null;
  const ok = all.filter((w) => w.status === "ok" && w.id !== f.id).map((w) => ({ w, km: distanceKm(f, w) }));
  return ok.length ? ok.reduce((a, b) => (b.km < a.km ? b : a)) : null;
};

export default function WaterMap({ waterpoints, villages = [], reports = [], since = Infinity, focus, legend = false, className = "map" }:
  { waterpoints: Waterpoint[]; villages?: Village[]; reports?: LogEvent[]; since?: number; focus?: Place | null; legend?: boolean; className?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Record<number, L.CircleMarker>>({});
  const focused = useRef<string | null | undefined>(undefined);  // the focused message id; undefined = no view set yet
  const towns = useRef<Record<string, L.CircleMarker>>({});
  const routes = useRef<Record<string, L.Polyline>>({});  // a red line per way with a danger on it, "village|point"
  const msgs = useRef<Record<string, { mark: L.Marker; html: string }>>({});  // one symbol per message id
  const alt = useRef<{ id: number; from: Waterpoint; km: number } | null>(null);  // the alternative shown for a down focus point
  const link = useRef<L.Polyline | null>(null);

  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: false, attributionControl: true });
    m.createPane("links").style.zIndex = "390";  // below the markers (overlayPane is 400): the line never crosses a dot
    m.createPane("hazards").style.zIndex = "620";  // the warning triangles sit above the water points
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, keepBuffer: 4, attribution: "&copy; OpenStreetMap" }).addTo(m);
    if (legend) {
      const lg = new L.Control({ position: "bottomright" });
      lg.onAdd = () => {
        const d = L.DomUtil.create("div", "legend");
        d.innerHTML = Object.entries(COLOR).map(([k, c]) => `<i style="background:${c}"></i>${k}`).join("<br>")
          + '<br><span class="lg-badge">' + badge("broken") + "</span>a report (one per message)"
          + '<br><i class="lg-village"></i>village a call named<br><span class="lg-hazard">' + TRIANGLE + "</span>danger on the way"
          + '<a href="/api/dashboard">dashboard</a>';
        return d;
      };
      lg.addTo(m);
    }
    map.current = m;
    // the container gets its size from the grid after mount: tell Leaflet once it is laid out, and on every resize
    const fix = () => m.invalidateSize();
    requestAnimationFrame(fix);
    const ro = new ResizeObserver(fix);
    ro.observe(el.current!);
    return () => { ro.disconnect(); m.remove(); map.current = null; markers.current = {}; towns.current = {}; routes.current = {}; msgs.current = {}; focused.current = undefined; };
  }, [legend]);

  // villages: the tiles already name them, so only the focused village gets a dot (CSS: .vdot)
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const v of villages) {
      if (towns.current[v.name]) continue;
      towns.current[v.name] = L.circleMarker([v.lat, v.lon], { radius: 5, weight: 2, color: "#1b2430", fillColor: "#ffffff", fillOpacity: 1, interactive: false, className: "vdot" }).addTo(m);
    }
  }, [villages]);

  // messages: a badge per status report next to its water point, a triangle per danger on its red route; new ones drop in
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const at: Record<string, LogEvent[]> = {};  // oldest first, so a symbol keeps its slot when newer ones arrive
    for (const e of [...reports].reverse()) (at[e.kind === "hazard" ? `${e.village}|${e.point}` : `${e.point}`] ??= []).push(e);
    for (const [key, es] of Object.entries(at)) {
      const w = waterpoints.find((x) => x.name === es[0].point), v = villages.find((x) => x.name === es[0].village);
      if (!w) continue;
      const hazard = es[0].kind === "hazard";
      if (hazard && !v) continue;
      if (hazard && !routes.current[key])
        routes.current[key] = L.polyline([[v!.lat, v!.lon], [w.lat, w.lon]], { pane: "links", color: "#d92d20", weight: 3, dashArray: "6 7", lineCap: "round", opacity: 0.85 }).addTo(m);
      es.slice(-FAN.length).forEach((e, k) => {
        const html = messagePopup(e), had = msgs.current[e.id];
        if (had) { if (had.html !== html) { had.mark.setPopupContent(html); had.html = html; } return; }
        const fresh = Number(e.id) > since ? " msg-new" : "";
        let pos: [number, number], icon: L.DivIcon;
        if (hazard) {  // along the route, around its middle
          const t = Math.min(0.85, Math.max(0.15, 0.5 + 0.13 * FAN[k]));
          pos = [v!.lat + (w.lat - v!.lat) * t, v!.lon + (w.lon - v!.lon) * t];
          icon = L.divIcon({ html: TRIANGLE, className: "hz" + fresh, iconSize: [30, 27], iconAnchor: [15, 22] });
        } else {  // the first one inside the water point's circle, further ones on a small circle around it
          const a = -Math.PI / 2 + FAN[k] * 0.75, r = k === 0 ? 0 : 24;
          pos = [w.lat, w.lon];
          icon = L.divIcon({ html: badge(e.detail && e.detail in COLOR ? (e.detail as Status) : "broken"), className: "msg" + fresh, iconSize: [20, 20],
                             iconAnchor: [10 - Math.round(r * Math.cos(a)), 10 - Math.round(r * Math.sin(a))] });
        }
        const mark = L.marker(pos, { pane: "hazards", keyboard: true, title: hazard ? "Danger on the way" : `Report: ${e.point} ${e.detail}`, icon })
          .bindPopup(html, { closeButton: false, autoPan: false, autoClose: false, className: hazard ? "hz-pop below" : "hz-pop" }).addTo(m);
        msgs.current[e.id] = { mark, html };
      });
    }
  }, [reports, villages, waterpoints, since]);

  // markers follow the data; the whole set is fitted once, and again whenever the focus goes away
  useEffect(() => {
    const m = map.current;
    if (!m || !waterpoints.length) return;
    for (const w of waterpoints) {
      const mk = markers.current[w.id];
      const style = { color: COLOR[w.status], fillColor: COLOR[w.status] };
      const html = alt.current?.id === w.id ? popup(w, alt.current.from, alt.current.km) : popup(w);
      if (mk) mk.setStyle(style).setPopupContent(html);
      else markers.current[w.id] = L.circleMarker([w.lat, w.lon], { radius: 9, weight: 3, fillOpacity: 0.6, ...style })
        .bindPopup(html, { closeButton: false, autoPan: false, autoClose: false }).addTo(m);
    }
    const id = focus ? focus.id : null;
    if (id === focused.current) return;  // first run: focused is undefined, so the view is always set once
    const first = focused.current === undefined;
    if (first) {  // the overview of all points is as far out as it goes, and the view stays around them
      const all = L.latLngBounds(waterpoints.map((w) => [w.lat, w.lon] as [number, number]));
      m.setMinZoom(m.getBoundsZoom(all, false, L.point(40, 40))); m.setMaxBounds(all.pad(0.6));
    }
    focused.current = id;
    m.invalidateSize();
    // the view comes first: Leaflet projects markers only once the map has a view, and setStyle on an unprojected marker throws
    link.current?.remove(); link.current = null;
    for (const mk of Object.values(markers.current)) mk.closePopup();
    for (const d of Object.values(msgs.current)) d.mark.closePopup();
    const mark = (t: L.CircleMarker | undefined, on: boolean) => t?.getElement()?.classList.toggle("on", on);
    for (const t of Object.values(towns.current)) mark(t, false);
    if (focus) {
      const { village, point } = focus;
      const near = point ? nearestWorking(point, waterpoints) : null;
      alt.current = near && point ? { id: near.w.id, from: point, km: near.km } : null;
      const own = msgs.current[focus.id];  // the message's own symbol, when it is a report
      const danger = village && point ? routes.current[`${village.name}|${point.name}`] : undefined;
      // a water point (and its alternative), a danger (and the working water point the reply named instead, like graph.avoid),
      // or a village's two nearest water points
      const instead = danger ? nearestTo(village!, waterpoints.filter((w) => w.status === "ok" && w.id !== point!.id), 1) : [];
      const shown = point ? [point, ...(near ? [near.w] : []), ...instead] : nearestTo(village!, waterpoints, 2);
      const big = new Set(shown.map((w) => w.id));
      if (near && point) {
        markers.current[near.w.id]?.setPopupContent(popup(near.w, point, near.km));
        link.current = L.polyline([[point.lat, point.lon], [near.w.lat, near.w.lon]], { pane: "links", color: "#5a6470", weight: 2, dashArray: "2 7", lineCap: "round", opacity: 0.7 }).addTo(m);
      }
      if (village && point && !danger && !near)  // the way the caller named, dark dotted; a reported danger has its own red one
        link.current = L.polyline([[village.lat, village.lon], [point.lat, point.lon]], { pane: "links", color: "#1b2430", weight: 2.5, dashArray: "2 7", lineCap: "round", opacity: 0.8 }).addTo(m);
      const corners = [...shown, ...(village ? [village] : [])].map((p) => [p.lat, p.lon] as [number, number]);
      const bounds = L.latLngBounds(corners);
      if (first) m.fitBounds(bounds, { padding: [80, 80], maxZoom: 15 });
      else glide(m, bounds.getCenter(), Math.min(15, m.getBoundsZoom(bounds, false, L.point(80, 80))));
      for (const [k, other] of Object.entries(markers.current)) {
        const hi = big.has(Number(k));
        other.setStyle({ radius: hi ? 14 : 7, weight: hi ? 4 : 2, fillOpacity: hi ? 0.95 : 0.6 });
      }
      const open = () => {
        if (focused.current !== id) return;  // a newer message came in while the map was still moving here
        if (village) mark(towns.current[village.name], true);
        if (own) own.mark.openPopup();
        if (danger) instead.forEach((w) => markers.current[w.id]?.openPopup());
        else shown.filter((w) => !own || w.id !== point?.id).forEach((w) => markers.current[w.id]?.openPopup());
      };
      if (first) open(); else m.once("moveend", open);
    } else {
      alt.current = null;
      const bounds = L.latLngBounds(waterpoints.map((w) => [w.lat, w.lon] as [number, number]));
      if (first) m.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      else glide(m, bounds.getCenter(), Math.min(14, m.getBoundsZoom(bounds, false, L.point(40, 40))));
      for (const mk of Object.values(markers.current)) { mk.setStyle({ radius: 9, weight: 3, fillOpacity: 0.6 }); mk.closePopup(); }
    }
  }, [waterpoints, focus]);

  return <div className={className} ref={el} />;
}
