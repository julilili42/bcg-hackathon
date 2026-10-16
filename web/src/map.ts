import maplibregl, { type ExpressionSpecification, type Map as MlMap, type MapGeoJSONFeature } from "maplibre-gl";
import type { Domain, Feature, FeatureCollection, StatusRole } from "./types";
import { roleFor } from "./types";

const SOURCE = "entities";
const ROLES: StatusRole[] = ["good", "warning", "serious", "disputed", "unknown"];

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function roleColors(): Record<StatusRole, string> {
  return {
    good: cssVar("--status-good"),
    warning: cssVar("--status-warning"),
    serious: cssVar("--status-serious"),
    disputed: cssVar("--status-disputed"),
    unknown: cssVar("--status-unknown"),
  };
}

function colorExpression(): ExpressionSpecification {
  const colors = roleColors();
  const branches: (string | string[])[] = [];
  for (const role of ROLES) branches.push(role, colors[role]);
  return ["match", ["get", "role"], ...branches, colors.unknown] as unknown as ExpressionSpecification;
}

export interface MapHandlers {
  onSelect: (id: string) => void;
}

export class EntityMap {
  private map: MlMap;
  private ready: Promise<void>;
  private popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
  private fitted = false;

  constructor(container: string, private handlers: MapHandlers) {
    this.map = new maplibregl.Map({
      container,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [38.9, -7.05],
      zoom: 9,
      attributionControl: false,
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    this.ready = new Promise((resolve) => this.map.on("load", () => resolve()));
    void this.ready.then(() => this.addLayers());
  }

  private addLayers(): void {
    this.map.addSource(SOURCE, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "id" });
    const color = colorExpression();
    this.map.addLayer({
      id: "flash",
      type: "circle",
      source: SOURCE,
      filter: ["==", ["get", "flash"], true],
      paint: { "circle-radius": 22, "circle-color": color, "circle-opacity": 0.25, "circle-blur": 0.4 },
    });
    this.map.addLayer({
      id: "points",
      type: "circle",
      source: SOURCE,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "served_population"], 100]], 0, 5, 10, 6, 40, 11],
        "circle-color": color,
        "circle-opacity": ["case", ["get", "verified"], 0.95, 0.5],
        "circle-stroke-color": cssVar("--surface-1"),
        "circle-stroke-width": 2,
      },
    });
    this.map.addLayer({
      id: "selected",
      type: "circle",
      source: SOURCE,
      filter: ["==", ["get", "selected"], true],
      paint: { "circle-radius": 16, "circle-color": "transparent", "circle-stroke-color": cssVar("--ink-1"), "circle-stroke-width": 2.5 },
    });
    this.map.on("mousemove", "points", (e) => this.hover(e.features?.[0]));
    this.map.on("mouseleave", "points", () => {
      this.map.getCanvas().style.cursor = "";
      this.popup.remove();
    });
    this.map.on("click", "points", (e) => {
      const feature = e.features?.[0];
      const id = feature?.properties?.id;
      if (typeof id === "string") this.handlers.onSelect(id);
    });
  }

  private hover(feature: MapGeoJSONFeature | undefined): void {
    if (!feature || feature.geometry.type !== "Point") return;
    this.map.getCanvas().style.cursor = "pointer";
    const p = feature.properties as Record<string, unknown>;
    const coords = feature.geometry.coordinates as [number, number];
    const verified = p.verified === true || p.verified === "true";
    const label = typeof p.label_en === "string" ? p.label_en : String(p.current_status);
    this.popup
      .setLngLat(coords)
      .setHTML(
        `<strong>${escapeHtml(String(p.name))}</strong><br/><span class="role-${String(p.role)}">${escapeHtml(label)}</span>` +
          (verified ? "" : ' <span class="muted">· unverified</span>'),
      )
      .addTo(this.map);
  }

  async setData(fc: FeatureCollection, domain: Domain | undefined, flashIds: Set<string>, selectedId: string | null): Promise<void> {
    await this.ready;
    const features: Feature[] = fc.features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        role: roleFor(domain, f.properties.current_status),
        label_en: f.properties.status_label.en,
        flash: flashIds.has(f.id),
        selected: f.id === selectedId,
      } as Feature["properties"],
    }));
    const source = this.map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
    source?.setData({ type: "FeatureCollection", features });
    if (!this.fitted && features.length > 0) {
      this.fitted = true;
      const bounds = new maplibregl.LngLatBounds();
      for (const f of features) bounds.extend(f.geometry.coordinates);
      this.map.fitBounds(bounds, { padding: 40, maxZoom: 12, duration: 0 });
    }
  }

  async flyTo(coords: [number, number]): Promise<void> {
    await this.ready;
    this.map.flyTo({ center: coords, zoom: Math.max(this.map.getZoom(), 13), duration: 700 });
  }

  refit(): void {
    this.fitted = false;
  }
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}
