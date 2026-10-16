// Leaflet map of the water points, the villages and the dangers reported on the way between them.
// `focus` = the place a call just named: the map flies there. A water point opens its popup, and when it is down the nearest
// working one is shown as the alternative (same straight-line walk as gateway/graph.py). A village alone shows its two nearest
// water points; a village and a water point show the way between them. Without focus it shows all points. OpenStreetMap tiles.
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { COLOR, HAZARD_LABEL, age, type Hazard, type Place, type Village, type Waterpoint } from "./api";

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
const TRIANGLE = '<svg viewBox="0 0 30 27" width="30" height="27" aria-hidden="true"><path d="M15 2 28.5 25.5h-27z" fill="#d92d20" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M15 10v7" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><circle cx="15" cy="21" r="1.6" fill="#fff"/></svg>';
const hazardPopup = (hs: Hazard[]) =>  // newest first; several reports on one way are counted
  `<b>${HAZARD_LABEL[hs[0].kind] ?? "Danger"} on the way</b> · ${esc(hs[0].village)} → ${esc(hs[0].point)}`
  + `<br><small>${esc(hs[0].body.slice(0, 90))}</small>`
  + `<br><small>Anonymous resident · ${age(hs[0].ts)}${hs.length > 1 ? ` · ${hs.length} reports` : ""}</small>`;
const nearestTo = (v: Village, all: Waterpoint[], n: number) =>
  all.map((w) => ({ w, km: distanceKm(v, w) })).sort((a, b) => a.km - b.km).slice(0, n).map((x) => x.w);

const nearestWorking = (f: Waterpoint, all: Waterpoint[]) => {
  if (f.status === "ok") return null;
  const ok = all.filter((w) => w.status === "ok" && w.id !== f.id).map((w) => ({ w, km: distanceKm(f, w) }));
  return ok.length ? ok.reduce((a, b) => (b.km < a.km ? b : a)) : null;
};

export default function WaterMap({ waterpoints, villages = [], hazards = [], focus, legend = false, className = "map" }:
  { waterpoints: Waterpoint[]; villages?: Village[]; hazards?: Hazard[]; focus?: Place | null; legend?: boolean; className?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Record<number, L.CircleMarker>>({});
  const focused = useRef<string | null | undefined>(undefined);  // "village|point"; undefined = no view set yet
  const towns = useRef<Record<string, L.CircleMarker>>({});
  const dangers = useRef<Record<string, { line: L.Polyline; mark: L.Marker; html: string }>>({});  // one per way, "village|point"
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
    return () => { ro.disconnect(); m.remove(); map.current = null; markers.current = {}; towns.current = {}; dangers.current = {}; focused.current = undefined; };
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

  // dangers on the way: a red dashed line from the village to the water point, a warning triangle halfway
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const byWay: Record<string, Hazard[]> = {};
    for (const h of hazards) (byWay[`${h.village}|${h.point}`] ??= []).push(h);
    for (const [key, hs] of Object.entries(byWay)) {
      const v = villages.find((x) => x.name === hs[0].village), w = waterpoints.find((x) => x.name === hs[0].point);
      if (!v || !w) continue;
      const html = hazardPopup(hs), d = dangers.current[key];
      if (d) { if (d.html !== html) { d.mark.setPopupContent(html); d.html = html; } continue; }
      const line = L.polyline([[v.lat, v.lon], [w.lat, w.lon]], { pane: "links", color: "#d92d20", weight: 3, dashArray: "6 7", lineCap: "round", opacity: 0.85 }).addTo(m);
      const mark = L.marker([(v.lat + w.lat) / 2, (v.lon + w.lon) / 2], { pane: "hazards", keyboard: true, title: "Danger on the way",
        icon: L.divIcon({ html: TRIANGLE, className: "hz", iconSize: [30, 27], iconAnchor: [15, 22] }) })
        .bindPopup(html, { closeButton: false, autoPan: false, autoClose: false, className: "hz-pop" }).addTo(m);
      dangers.current[key] = { line, mark, html };
    }
  }, [hazards, villages, waterpoints]);

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
    const id = focus ? `${focus.village?.name ?? ""}|${focus.point?.name ?? ""}` : null;
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
    for (const d of Object.values(dangers.current)) d.mark.closePopup();
    const mark = (t: L.CircleMarker | undefined, on: boolean) => t?.getElement()?.classList.toggle("on", on);
    for (const t of Object.values(towns.current)) mark(t, false);
    if (focus) {
      const { village, point } = focus;
      const near = point ? nearestWorking(point, waterpoints) : null;
      alt.current = near && point ? { id: near.w.id, from: point, km: near.km } : null;
      const danger = village && point ? dangers.current[`${village.name}|${point.name}`] : undefined;
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
        if (village) mark(towns.current[village.name], true);
        if (danger) { danger.mark.openPopup(); instead.forEach((w) => markers.current[w.id]?.openPopup()); }
        else shown.forEach((w) => markers.current[w.id]?.openPopup());
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
