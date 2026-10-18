import { useEffect, useMemo, useRef, useState } from "react";

export type Status = "ok" | "broken" | "empty";
export type Waterpoint = { id: number; name: string; village: string; lat: number; lon: number; status: Status; updated: string };
export type LogEvent = { id: string; ts: string; channel: "sms" | "voice" | "api"; sender: string; lang: "sw" | "en" | "de" | "fr"; body: string; reply: string;
  village: string | null; point: string | null;  // the place the turn was about
  kind: "status" | "hazard" | "query" | null; detail: string | null };  // status: ok/broken/empty; hazard: its kind
export type Village = { name: string; lat: number; lon: number };
export type HazardKind = "harassment" | "blocked" | "animals" | "other";
export type Hazard = { id: string; ts: string; village: string; point: string; kind: HazardKind; body: string };  // anonymous: no sender
export type Events = { events: LogEvent[]; waterpoints: Waterpoint[]; villages: Village[]; hazards: Hazard[] };
/** What the map shows up close: a village, a water point, or both (a route), for the message `id`. */
export type Place = { village: Village | null; point: Waterpoint | null; id: string };
/** A message the viewer clicked: shown until a newer message than `after` arrives. */
export type Picked = { id: string; after: number };
/** Every status or hazard report is one message in the feed and one symbol on the map. */
export const isReport = (e: LogEvent) => (e.kind === "status" || e.kind === "hazard") && !!e.point;

export const HAZARD_LABEL: Record<HazardKind, string> = { harassment: "Harassment", blocked: "Path blocked", animals: "Animals", other: "Danger" };

export const COLOR: Record<Status, string> = { ok: "#2fbf5b", broken: "#e0483f", empty: "#e2a33a" };

/** Polls /api/events every `ms`. Keeps the last good answer when the host is down. */
export function useEvents(ms: number): Events {
  const [data, setData] = useState<Events>({ events: [], waterpoints: [], villages: [], hazards: [] });
  useEffect(() => {
    const load = () => fetch("/api/events").then((r) => r.json()).then((d) => setData({ villages: [], hazards: [], ...d })).catch(() => {});
    load();
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [ms]);
  return data;
}

/** Newest event id when the page opened: messages after it are new (they animate in and move the map). */
export function useSince(data: Events): number {
  const since = useRef<number | null>(null);
  if (since.current === null && data.waterpoints.length) since.current = Math.max(0, ...data.events.map((e) => Number(e.id)));
  return since.current ?? Infinity;
}

/** The place the newest call or message named, once one arrives after the page opened (until then: the overview),
 *  or the message the viewer clicked, until a newer one arrives. Every new message moves the map to its place. */
export function useFocus(data: Events, picked?: Picked | null): Place | null {
  const since = useSince(data);
  const newest = data.events.find((e) => Number(e.id) > since && (e.village || e.point));
  const pick = picked && !(newest && Number(newest.id) > picked.after) ? data.events.find((e) => e.id === picked.id) : undefined;
  const e = pick ?? newest;
  const point = (e && data.waterpoints.find((w) => w.name === e.point)) || null;
  const village = (e && data.villages.find((v) => v.name === (e.village ?? point?.village))) || null;
  // the same place keeps the same object, so the map does not fly again; a new status of the point does count
  return useMemo(() => (e && (point || village) ? { village, point, id: e.id } : null),
    [e?.id, point?.status, !!village]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** "2025-10-16 17:03:11" (UTC, from SQL) -> "4m ago" */
export function age(ts: string) {
  const s = Math.max(0, Math.round((Date.now() - new Date(ts.replace(" ", "T") + "Z").getTime()) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`;
}
