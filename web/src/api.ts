import type { Domain, EntityDetail, FeatureCollection, Health, Interaction, Report, ReportCreated, Stats } from "./types";

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => get<Health>("/api/health"),
  domains: () => get<Domain[]>("/api/domains"),
  entities: (domain: string) => get<FeatureCollection>(`/api/entities?domain=${encodeURIComponent(domain)}`),
  entity: (id: string) => get<EntityDetail>(`/api/entities/${encodeURIComponent(id)}`),
  stats: (domain: string) => get<Stats>(`/api/stats?domain=${encodeURIComponent(domain)}`),
  reports: (domain: string, limit = 30) =>
    get<Report[]>(`/api/reports?domain=${encodeURIComponent(domain)}&limit=${limit}`),
  interactions: (limit = 30) => get<Interaction[]>(`/api/interactions?limit=${limit}`),
  async createReport(body: { entity_id: string; status: string; note?: string; lang?: string }): Promise<ReportCreated> {
    const res = await fetch("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))) as { detail?: string };
      throw new Error(detail.detail ?? `${res.status}`);
    }
    return (await res.json()) as ReportCreated;
  },
};
