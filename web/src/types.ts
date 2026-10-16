export type Lang = "sw" | "en";
export type Channel = "voice" | "sms" | "web" | "import";
export type StatusRole = "good" | "warning" | "serious" | "disputed" | "unknown";

export interface Health {
  status: string;
  version: string;
  domains: string[];
  entities: number;
  understanding: string;
  tts: string;
  demo_phone: boolean;
  time: string;
}

export interface Domain {
  id: string;
  entity_type: string;
  names: Record<string, string>;
  good_statuses: string[];
  bad_statuses: string[];
  status_labels: Record<string, Record<string, string>>;
}

export interface EntityProps {
  id: string;
  domain_id: string;
  name: string;
  aliases: string[];
  adm1?: string | null;
  adm2?: string | null;
  adm3?: string | null;
  attributes: Record<string, unknown>;
  source: string;
  external_id?: string | null;
  current_status: string;
  confidence: number;
  last_report_at?: string | null;
  served_population?: number | null;
  verified: boolean;
  status_label: { en: string; sw: string };
  is_good: boolean;
}

export interface Feature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: EntityProps;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

export interface Report {
  id: number;
  entity_id: string;
  entity_name?: string | null;
  domain_id?: string | null;
  reporter_hash: string;
  channel: Channel;
  lang?: string | null;
  raw_text?: string | null;
  status_claimed: string;
  note?: string | null;
  weight: number;
  created_at: string;
}

export interface Alternative {
  entity_id: string;
  name: string;
  distance_km: number;
  walk_minutes: number;
  status: string;
  confidence: number;
  verified: boolean;
}

export interface EntityDetail {
  entity: Feature;
  reports: Report[];
  alternatives: Alternative[];
}

export interface Stats {
  domain_id: string;
  total: number;
  by_status: Record<string, number>;
  people_affected: number;
  verified: number;
  unverified: number;
  disputed: number;
  reports_24h: number;
}

export interface Interaction {
  id: number;
  channel: Channel;
  sender_hash: string;
  lang?: string | null;
  body: string;
  reply: string;
  intent: string;
  entity_id?: string | null;
  latency_ms: number;
  created_at: string;
}

export interface ReportCreated {
  entity: Feature;
  derived: { status: string; confidence: number; report_count: number; votes: Record<string, number> };
  alternatives: Alternative[];
}

const WARNING_STATUSES = new Set(["empty", "no_stock"]);

export function roleFor(domain: Domain | undefined, status: string): StatusRole {
  if (status === "disputed") return "disputed";
  if (status === "unknown") return "unknown";
  if (domain?.good_statuses.includes(status)) return "good";
  if (WARNING_STATUSES.has(status)) return "warning";
  if (domain?.bad_statuses.includes(status)) return "serious";
  return "unknown";
}

export const ROLE_ICON: Record<StatusRole, string> = {
  good: "✓",
  warning: "!",
  serious: "✕",
  disputed: "?",
  unknown: "·",
};
