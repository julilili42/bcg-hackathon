import { useEffect, useState } from "react";

export type Status = "ok" | "broken" | "empty";
export type Pos = { lat: number; lon: number };
export type Waterpoint = Pos & { id: number; name: string; village: string; status: Status; updated: string };
export type LogEvent = { id: string; ts: string; channel: "sms" | "voice"; sender: string; lang: "sw" | "en"; body: string; reply: string };
/** A caller who said where they stand and which water point they cannot get water from; alt_id = the working one the brain sent them to.
 *  blocked: the way there is blocked (the pump itself may work); otherwise the pump is down. See gateway/db.py. */
export type Incident = Pos & { id: number; ts: string; place: string; wp_id: number; alt_id: number | null; blocked: boolean };
export type Events = { events: LogEvent[]; waterpoints: Waterpoint[]; incidents: Incident[] };

export const COLOR: Record<Status, string> = { ok: "#2fbf5b", broken: "#e0483f", empty: "#e2a33a" };

/** Polls /api/events every `ms`. Keeps the last good answer when the host is down. */
export function useEvents(ms: number): Events {
  const [data, setData] = useState<Events>({ events: [], waterpoints: [], incidents: [] });
  useEffect(() => {
    const load = () => fetch("/api/events").then((r) => r.json()).then((d) => setData({ incidents: [], ...d })).catch(() => {});
    load();
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [ms]);
  return data;
}

/** "2025-10-16 17:03:11" (UTC, from SQL) -> "4m ago" */
export function age(ts: string) {
  const s = Math.max(0, Math.round((Date.now() - new Date(ts.replace(" ", "T") + "Z").getTime()) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`;
}

/** Great-circle km, like db.distance_km: a straight line, roads are longer. */
export const distanceKm = (a: Pos, b: Pos) => {
  const r = Math.PI / 180, p1 = a.lat * r, p2 = b.lat * r, dp = p2 - p1, dl = (b.lon - a.lon) * r;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
};
/** Walking at 4 km/h, rounded to 5 minutes, never 0: like db.walk_minutes. */
export const walkMinutes = (km: number) => Math.max(5, 5 * Math.round(km / 4 * 60 / 5));
