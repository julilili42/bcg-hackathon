import { useEffect, useState } from "react";

export type Status = "ok" | "broken" | "empty";
export type Waterpoint = { id: number; name: string; village: string; lat: number; lon: number; status: Status; updated: string };
export type LogEvent = { id: string; ts: string; channel: "sms" | "voice"; sender: string; lang: "sw" | "en"; body: string; reply: string };
export type Events = { events: LogEvent[]; waterpoints: Waterpoint[] };

export const COLOR: Record<Status, string> = { ok: "#2fbf5b", broken: "#e0483f", empty: "#e2a33a" };

/** Polls /api/events every `ms`. Keeps the last good answer when the host is down. */
export function useEvents(ms: number): Events {
  const [data, setData] = useState<Events>({ events: [], waterpoints: [] });
  useEffect(() => {
    const load = () => fetch("/api/events").then((r) => r.json()).then(setData).catch(() => {});
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
