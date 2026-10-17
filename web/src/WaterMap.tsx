// Leaflet map of the water points. `focus` = the point a call just touched: the map flies there and opens its popup;
// when that point is down, the nearest working one is shown as the alternative (same straight-line walk as gateway/graph.py).
// `incident` = a caller who said where they stand and which water point they cannot get water from: a pulsing marker
// where they are, the way to that point (red when blocked or down) and the working alternative the brain sent them to.
// Without either it shows all points. OpenStreetMap tiles.
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { COLOR, distanceKm, walkMinutes, type Incident, type Waterpoint } from "./api";

// Leaflet's flyTo follows a flight path that overshoots the target zoom and comes back when the pan is short, and it
// scales the markers up to 8x on the way. glide() moves zoom and centre monotonically with one ease-in-out and
// redraws the markers every frame, so they keep their size. Uses the same map internals flyTo itself uses.
function glide(m: L.Map, target: L.LatLng, zoom: number, duration = 2.0) {
  const map = m as unknown as { _stop(): void; _moveStart(z: boolean, n: boolean): void; _move(c: L.LatLng, z: number): L.Map & { _moveEnd(z: boolean): void }; _renderer?: { _reset(): void }; _flyToFrame?: number };
  map._stop();
  const z0 = m.getZoom(), c0 = m.project(m.getCenter(), zoom), c1 = m.project(target, zoom);
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
const popup = (w: Waterpoint, note?: string) =>  // one line; a focused point gets a second, small one
  `<b>${esc(w.name)}</b> · ${esc(w.village)}` + (note ? `<br><small>${esc(note)}</small>` : "");  // the status is the marker's colour
const nearestWorking = (f: Waterpoint, all: Waterpoint[]) => {
  if (f.status === "ok") return null;
  const ok = all.filter((w) => w.status === "ok" && w.id !== f.id).map((w) => ({ w, km: distanceKm(f, w) }));
  return ok.length ? ok.reduce((a, b) => (b.km < a.km ? b : a)) : null;
};
const callerIcon = (place: string) =>  // the caller: a blue dot with a pulsing ring and the place they named (app.css .me)
  L.divIcon({ className: "me", iconSize: [16, 16], iconAnchor: [8, 8], html: `<i class="ring"></i><i class="dot"></i><span class="tag">${esc(place)}</span>` });
const GREY = "#5a6470";

export default function WaterMap({ waterpoints, focus, incident, legend = false, className = "map" }:
  { waterpoints: Waterpoint[]; focus?: Waterpoint | null; incident?: Incident | null; legend?: boolean; className?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Record<number, L.CircleMarker>>({});
  const shown = useRef<string | null | undefined>(undefined);  // what the view is on: "w<id>" | "i<id>" | null; undefined = no view set yet
  const notes = useRef<Record<number, string>>({});           // second popup line per water point while something is focused
  const layers = useRef<L.Layer[]>([]);                       // the lines and the caller marker of the current focus

  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: false, attributionControl: true });
    m.createPane("links").style.zIndex = "390";  // below the markers (overlayPane is 400): the line never crosses a dot
    m.createPane("caller").style.zIndex = "750";  // above the popups (700): the caller is never hidden behind one
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, keepBuffer: 4, attribution: "&copy; OpenStreetMap" }).addTo(m);
    if (legend) {
      const lg = new L.Control({ position: "bottomright" });
      lg.onAdd = () => {
        const d = L.DomUtil.create("div", "legend");
        d.innerHTML = Object.entries(COLOR).map(([k, c]) => `<i style="background:${c}"></i>${k}`).join("<br>") + '<a href="/api/dashboard">dashboard</a>';
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
    return () => { ro.disconnect(); m.remove(); map.current = null; markers.current = {}; shown.current = undefined; notes.current = {}; layers.current = []; };
  }, [legend]);

  // markers follow the data; the whole set is fitted once, and again whenever the focus goes away
  useEffect(() => {
    const m = map.current;
    if (!m || !waterpoints.length) return;
    for (const w of waterpoints) {
      const mk = markers.current[w.id];
      const style = { color: COLOR[w.status], fillColor: COLOR[w.status] };
      const html = popup(w, notes.current[w.id]);
      if (mk) mk.setStyle(style).setPopupContent(html);
      else markers.current[w.id] = L.circleMarker([w.lat, w.lon], { radius: 9, weight: 3, fillOpacity: 0.6, ...style })
        .bindPopup(html, { closeButton: false, autoPan: false, autoClose: false }).addTo(m);
    }
    const key = incident ? `i${incident.id}` : focus ? `w${focus.id}` : null;
    if (key === shown.current) return;  // first run: shown is undefined, so the view is always set once
    const first = shown.current === undefined;
    if (first) {  // the overview of all points is as far out as it goes, and the view stays around them
      const all = L.latLngBounds(waterpoints.map((w) => [w.lat, w.lon] as [number, number]));
      m.setMinZoom(m.getBoundsZoom(all, false, L.point(40, 40))); m.setMaxBounds(all.pad(0.6));
    }
    shown.current = key;
    m.invalidateSize();
    // the view comes first: Leaflet projects markers only once the map has a view, and setStyle on an unprojected marker throws
    for (const l of layers.current) l.remove();
    layers.current = []; notes.current = {};
    for (const mk of Object.values(markers.current)) mk.closePopup();
    const line = (a: L.LatLngExpression, b: L.LatLngExpression, color: string, dashed = true) => layers.current.push(
      L.polyline([a, b], { pane: "links", color, weight: dashed ? 2.5 : 3.5, dashArray: dashed ? "2 8" : undefined, lineCap: "round", opacity: 0.8 }).addTo(m));
    const byId = Object.fromEntries(waterpoints.map((w) => [w.id, w]));
    const big: Waterpoint[] = [], anchors: L.LatLngExpression[] = [];
    if (incident) {
      const here: L.LatLngExpression = [incident.lat, incident.lon];
      const wp = byId[incident.wp_id], alt = incident.alt_id == null ? undefined : byId[incident.alt_id];
      anchors.push(here);
      layers.current.push(L.marker(here, { icon: callerIcon(incident.place), pane: "caller", interactive: false }).addTo(m));
      if (wp) {
        big.push(wp); notes.current[wp.id] = incident.blocked ? `way blocked from ${incident.place}` : `${wp.status} · from ${incident.place}`;
        line(here, [wp.lat, wp.lon], incident.blocked || wp.status !== "ok" ? COLOR.broken : GREY);
      }
      if (alt) {
        big.push(alt); notes.current[alt.id] = `go here: ~${walkMinutes(distanceKm(incident, alt))} min from ${incident.place}`;
        line(here, [alt.lat, alt.lon], COLOR.ok, false);
      }
    } else if (focus) {
      const near = nearestWorking(focus, waterpoints);
      big.push(focus);
      if (near) {
        big.push(near.w); notes.current[near.w.id] = `~${walkMinutes(near.km)} min from ${focus.name}`;
        line([focus.lat, focus.lon], [near.w.lat, near.w.lon], GREY);
      }
    }
    for (const w of big) { markers.current[w.id]?.setPopupContent(popup(w, notes.current[w.id])); anchors.push([w.lat, w.lon]); }
    if (anchors.length) {
      const bounds = L.latLngBounds(anchors), ids = new Set(big.map((w) => w.id));
      if (first) m.fitBounds(bounds, { padding: [80, 80], maxZoom: 16 });
      else glide(m, bounds.getCenter(), Math.min(16, m.getBoundsZoom(bounds, false, L.point(80, 80))));
      for (const [k, other] of Object.entries(markers.current)) {
        const hi = ids.has(Number(k));
        other.setStyle({ radius: hi ? 14 : 7, weight: hi ? 4 : 2, fillOpacity: hi ? 0.95 : 0.6 });
      }
      const open = () => big.forEach((w) => markers.current[w.id]?.openPopup());
      if (first) open(); else m.once("moveend", open);
    } else {
      const bounds = L.latLngBounds(waterpoints.map((w) => [w.lat, w.lon] as [number, number]));
      if (first) m.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      else glide(m, bounds.getCenter(), Math.min(14, m.getBoundsZoom(bounds, false, L.point(40, 40))));
      for (const mk of Object.values(markers.current)) { mk.setStyle({ radius: 9, weight: 3, fillOpacity: 0.6 }); mk.closePopup(); }
    }
  }, [waterpoints, focus, incident]);

  return <div className={className} ref={el} />;
}
