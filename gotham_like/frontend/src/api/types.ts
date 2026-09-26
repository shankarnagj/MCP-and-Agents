export type EpistemicStatus = "RAW" | "DERIVED" | "ANALYST_ASSERTION" | "SYSTEM_INFERENCE" | "VERIFIED";

export interface EntitySummary {
  id: string;
  type: string;
  label: string;
  confidence: number;
  epistemic_status: EpistemicStatus;
  lat: number | null;
  lon: number | null;
  observed_at: string | null;
  hop?: number;
  score?: number;
  distance_m?: number | null;
  preview?: Record<string, unknown>;
}

export interface EntityDetail extends EntitySummary {
  properties: Record<string, unknown>;
  masked_fields: string[];
  source_ids: string[];
  provenance: Record<string, unknown> & { resolution?: ResolutionEntry[] };
  classification: string;
  created_at: string;
  updated_at: string;
  redirected_from: string | null;
  degree: Record<string, number>;
  signals: { id: string; label: string; rule_id: string; score: number; what: string; created_at: string }[];
  open_alerts: number;
  assertions: { id: string; statement: string; status: string; epistemic_status: string }[];
  resolution_candidates: { id: string; other: string; decision: string; score: number; review_status: string; merged: boolean }[];
}

export interface ResolutionEntry {
  merged: string;
  score: number;
  decision: string;
  reasons: string[];
  resolver_version: string;
  epistemic_status: string;
}

export interface Edge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  timestamp: string | null;
  confidence: number;
  epistemic_status: EpistemicStatus;
  properties: Record<string, unknown>;
  source_records: string[];
  provenance: Record<string, unknown>;
  analyst_modifications?: Record<string, unknown>[];
}

export interface GraphPayload {
  nodes: EntitySummary[];
  edges: Edge[];
  truncated?: boolean;
  truncation_reasons?: string[];
  hops?: { hop: number; frontier: number; edges: number; new_nodes: number }[];
}

export interface EventItem {
  id: string;
  event_type: string;
  timestamp: string;
  entity_ids: string[];
  location_id: string | null;
  lat: number | null;
  lon: number | null;
  source: string;
  source_record_id: string | null;
  properties: Record<string, unknown>;
  epistemic_status: EpistemicStatus;
  distance_m?: number | null;
}

export interface TimelineResponse {
  events: EventItem[];
  total: number;
  span: { from: string | null; to: string | null };
  histogram: { bucket: string; series: { t: string; counts: Record<string, number>; total: number }[] };
  by_type: Record<string, number>;
  simultaneous: { window_seconds: number; groups: { start: string; end: string; event_ids: string[]; event_types: string[]; shared_entities: string[] }[] };
}

export interface SearchResponse {
  query: string;
  parsed: Record<string, unknown> & { warnings: string[] };
  results: EntitySummary[];
  total_estimate: number;
  facets: { type: Record<string, number> };
  match_reasons: string[];
  note: string;
}

export interface Signal {
  id: string;
  label: string;
  rule_id: string;
  rule_version: number;
  entity_ids: string[];
  score: number;
  evidence: Record<string, unknown>[];
  explanation: {
    label: string;
    what_happened: string;
    why_shown: string;
    supporting_data: { evidence_items: number; source_records: string[]; source_records_total: number };
    data_collected: { ingested_from?: string; ingested_to?: string; source_records?: number };
    time_window: { start: string | null; end: string | null };
    assumptions: string[];
    uncertain: string[];
    alternative_explanations: string[];
    score_meaning: string;
  };
  window_start: string | null;
  window_end: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  rule: string;
  alert_type: string;
  severity: string;
  timestamp: string;
  entities: string[];
  summary: string;
  signal_id: string | null;
  status: string;
}

export interface Investigation {
  id: string;
  name: string;
  description: string;
  status: string;
  scope: Record<string, unknown>;
  collaborators: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface InvestigationItem {
  id: string;
  kind: string;
  ref_id: string | null;
  title: string;
  content: Record<string, unknown>;
  epistemic_status: EpistemicStatus;
  provenance: Record<string, unknown>;
  created_by: string;
  created_at: string;
}

export interface Assertion {
  id: string;
  statement: string;
  status: string;
  label: string;
  subject_ids: string[];
  rationale: string;
  analyst_confidence: string | null;
  created_by: string;
  created_at: string;
  history: { status: string; by: string; at: string; note: string }[];
}

export interface InvestigationFull extends Investigation {
  items: InvestigationItem[];
  assertions: Assertion[];
  saved_queries: Record<string, unknown>[];
  counts: Record<string, number>;
  can_write: boolean;
}

export interface Provenance {
  id: string;
  kind: string;
  why: string;
  epistemic_status: EpistemicStatus;
  object: Record<string, unknown>;
  source_records: {
    id: string;
    source: { id: string; name: string; kind: string; classification: string };
    source_record_id: string;
    record_type: string;
    ingestion_timestamp: string;
    transformation_version: string;
    content_hash: string;
    payload: Record<string, unknown> | string;
  }[];
  source_records_total: number;
  lineage_upstream: { nodes: string[]; edges: { from: string; to: string; transformation: string; transformation_version: string; at: string }[] };
  lineage_downstream: { nodes: string[]; edges: { from: string; to: string; transformation: string }[] };
  analyst_modifications?: Record<string, unknown>[];
  entity_resolution?: ResolutionEntry[];
}

export interface Me {
  id: string;
  username: string;
  role: string;
  permissions: string[];
}
