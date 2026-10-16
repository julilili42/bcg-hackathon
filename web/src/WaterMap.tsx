// Leaflet map of the water points. `focus` = the point a call just touched: the map flies there and opens its popup;
// when that point is down, the nearest working one is shown as the alternative (same straight-line walk as gateway/graph.py).
// Without focus it shows all points. OpenStreetMap tiles.
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { COLOR, type Waterpoint } from "./api";

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
const popup = (w: Waterpoint, from?: Waterpoint, km?: number) =>  // one line; the alternative gets a second, small one
  `<b>${esc(w.name)}</b> · ${esc(w.village)}`  // the status is the marker's colour
  + (from === undefined || km === undefined ? "" : `<br><small>~${walkMinutes(km)} min from ${esc(from.name)}</small>`);
const walkMinutes = (km: number) => Math.max(5, 5 * Math.round(km / 4 * 60 / 5));  // like db.walk_minutes: 4 km/h, rounded to 5

const distanceKm = (a: Waterpoint, b: Waterpoint) => {  // great-circle, like db.distance_km; walking at 4 km/h
  const r = Math.PI / 180, p1 = a.lat * r, p2 = b.lat * r, dp = p2 - p1, dl = (b.lon - a.lon) * r;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
};
const nearestWorking = (f: Waterpoint, all: Waterpoint[]) => {
  if (f.status === "ok") return null;
  const ok = all.filter((w) => w.status === "ok" && w.id !== f.id).map((w) => ({ w, km: distanceKm(f, w) }));
  return ok.length ? ok.reduce((a, b) => (b.km < a.km ? b : a)) : null;
};

export default function WaterMap({ waterpoints, focus, legend = false, className = "map" }:
  { waterpoints: Waterpoint[]; focus?: Waterpoint | null; legend?: boolean; className?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Record<number, L.CircleMarker>>({});
  const focused = useRef<number | null | undefined>(undefined);  // undefined = no view set yet
  const alt = useRef<{ id: number; from: Waterpoint; km: number } | null>(null);  // the alternative shown for a down focus point
  const link = useRef<L.Polyline | null>(null);

  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: false, attributionControl: true });
    m.createPane("links").style.zIndex = "390";  // below the markers (overlayPane is 400): the line never crosses a dot
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
    return () => { ro.disconnect(); m.remove(); map.current = null; markers.current = {}; focused.current = undefined; };
  }, [legend]);

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
    const id = focus?.id ?? null;
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
    if (focus) {
      const near = nearestWorking(focus, waterpoints);
      alt.current = near ? { id: near.w.id, from: focus, km: near.km } : null;
      const shown = [focus, ...(near ? [near.w] : [])];
      const big = new Set(shown.map((w) => w.id));
      if (near) {
        markers.current[near.w.id]?.setPopupContent(popup(near.w, focus, near.km));
        link.current = L.polyline([[focus.lat, focus.lon], [near.w.lat, near.w.lon]], { pane: "links", color: "#5a6470", weight: 2, dashArray: "2 7", lineCap: "round", opacity: 0.7 }).addTo(m);
      }
      const bounds = L.latLngBounds(shown.map((w) => [w.lat, w.lon] as [number, number]));
      if (first) m.fitBounds(bounds, { padding: [80, 80], maxZoom: 16 });
      else glide(m, bounds.getCenter(), Math.min(16, m.getBoundsZoom(bounds, false, L.point(80, 80))));
      for (const [k, other] of Object.entries(markers.current)) {
        const hi = big.has(Number(k));
        other.setStyle({ radius: hi ? 14 : 7, weight: hi ? 4 : 2, fillOpacity: hi ? 0.95 : 0.6 });
      }
      const open = () => shown.forEach((w) => markers.current[w.id]?.openPopup());
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
