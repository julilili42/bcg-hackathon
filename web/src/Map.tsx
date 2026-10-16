import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { COLOR, useEvents } from "./api";

const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);

export default function MapPage() {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef<Record<number, L.CircleMarker>>({});
  const fitted = useRef(false);
  const { waterpoints } = useEvents(5000);

  useEffect(() => {
    const m = L.map(el.current!);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(m);
    const legend = new L.Control({ position: "bottomright" });
    legend.onAdd = () => {
      const d = L.DomUtil.create("div", "legend");
      d.innerHTML = Object.entries(COLOR).map(([k, c]) => `<i style="background:${c}"></i>${k}`).join("<br>") + '<a href="/api/dashboard">dashboard</a>';
      return d;
    };
    legend.addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; markers.current = {}; fitted.current = false; };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !waterpoints.length) return;
    for (const w of waterpoints) {
      const html = `<b>${esc(w.name)}</b><br>${esc(w.village)}<br><span style="color:${COLOR[w.status]}">${w.status}</span><br><small>${esc(w.updated)}</small>`;
      const mk = markers.current[w.id];
      if (mk) mk.setStyle({ color: COLOR[w.status] }).setPopupContent(html);
      else markers.current[w.id] = L.circleMarker([w.lat, w.lon], { radius: 9, color: COLOR[w.status], weight: 3, fillOpacity: 0.6 }).bindPopup(html).addTo(m);
    }
    if (!fitted.current) {
      m.fitBounds(waterpoints.map((w) => [w.lat, w.lon] as [number, number]), { padding: [40, 40], maxZoom: 14 });
      fitted.current = true;
    }
  }, [waterpoints]);

  return <div className="map" ref={el} />;
}
