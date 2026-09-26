/** Thin, typed API client. The bearer token lives in sessionStorage (cleared with the tab). */
import type {
  Alert, EntityDetail, Edge, GraphPayload, InvestigationFull, Investigation, Me, Provenance, SearchResponse, Signal, TimelineResponse,
} from "./types";

const TOKEN_KEY = "tessera.token";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export const auth = {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  set token(v: string | null) {
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  },
};

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export const onUnauthorized = (fn: Listener) => {
  unauthorizedListeners.add(fn);
  return () => {
    unauthorizedListeners.delete(fn);
  };
};

export function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
  return "Request failed";
}

export async function request<T>(method: string, path: string, body?: unknown, opts: { raw?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (auth.token) headers["Authorization"] = `Bearer ${auth.token}`;
  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  if (res.status === 401) {
    auth.token = null;
    unauthorizedListeners.forEach((l) => l());
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, formatDetail(detail), detail);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const qs = (params: Record<string, unknown>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
};

export interface GraphFilters {
  relationship_types?: string[] | null;
  direction?: "in" | "out" | "both";
  time_from?: string | null;
  time_to?: string | null;
  min_confidence?: number;
  neighbor_types?: string[] | null;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; user: { id: string; username: string; role: string } }>("POST", "/api/auth/login", { username, password }),
  logout: () => request("POST", "/api/auth/logout"),
  me: () => request<Me>("GET", "/api/auth/me"),
  stats: () => request<Record<string, any>>("GET", "/api/stats"),
  ontology: () => request<any>("GET", "/api/ontology"),
  search: (query: string, limit = 25) => request<SearchResponse>("POST", "/api/search", { query, limit }),
  entity: (id: string) => request<EntityDetail>("GET", `/api/entities/${encodeURIComponent(id)}`),
  relationships: (id: string, p: Record<string, unknown> = {}) =>
    request<{ items: (Edge & { other: any })[]; total: number; by_type: Record<string, number> }>("GET", `/api/entities/${encodeURIComponent(id)}/relationships${qs(p)}`),
  subgraph: (seeds: string[], depth: number, filters: GraphFilters = {}, max_nodes = 400, fanout = 100) =>
    request<GraphPayload>("POST", "/api/graph/subgraph", { seeds, depth, filters, max_nodes, fanout }),
  path: (body: Record<string, unknown>) => request<any>("POST", "/api/graph/path", body),
  analytics: (seeds: string[], algorithms: string[], depth = 2) => request<any>("POST", "/api/graph/analytics", { seeds, algorithms, depth }),
  timeline: (p: Record<string, unknown>) => request<TimelineResponse>("GET", `/api/timeline${qs(p)}`),
  geoQuery: (body: Record<string, unknown>) => request<any>("POST", "/api/geo/query", body),
  heatmap: (p: Record<string, unknown>) => request<any>("GET", `/api/geo/heatmap${qs(p)}`),
  geofences: () => request<any>("GET", "/api/geo/geofences"),
  trajectory: (id: string) => request<any>("GET", `/api/geo/trajectory/${encodeURIComponent(id)}`),
  provenance: (id: string) => request<Provenance>("GET", `/api/provenance/${encodeURIComponent(id)}`),
  reviewRelationship: (id: string, action: string, note: string) => request<Edge>("POST", `/api/relationships/${id}/review`, { action, note }),
  alerts: (status?: string) => request<{ items: Alert[]; counts: Record<string, number> }>("GET", `/api/alerts${qs({ status })}`),
  patchAlert: (id: string, status: string, note = "") => request<Alert>("PATCH", `/api/alerts/${id}`, { status, note }),
  signals: (p: Record<string, unknown> = {}) => request<{ items: Signal[] }>("GET", `/api/signals${qs(p)}`),
  signal: (id: string) => request<Signal>("GET", `/api/signals/${id}`),
  investigations: () => request<Investigation[]>("GET", "/api/investigations"),
  investigation: (id: string) => request<InvestigationFull>("GET", `/api/investigations/${id}`),
  createInvestigation: (name: string, description: string, scope: Record<string, unknown> = {}) =>
    request<Investigation>("POST", "/api/investigations", { name, description, scope }),
  patchInvestigation: (id: string, body: Record<string, unknown>) => request<Investigation>("PATCH", `/api/investigations/${id}`, body),
  addItem: (id: string, body: Record<string, unknown>) => request<any>("POST", `/api/investigations/${id}/items`, body),
  removeItem: (id: string, itemId: string) => request<void>("DELETE", `/api/investigations/${id}/items/${itemId}`),
  createAssertion: (body: Record<string, unknown>) => request<any>("POST", "/api/assertions", body),
  patchAssertion: (id: string, body: Record<string, unknown>) => request<any>("PATCH", `/api/assertions/${id}`, body),
  query: (pattern: Record<string, unknown>, explain = false) => request<any>("POST", "/api/query", { pattern, explain }),
  saveQuery: (body: Record<string, unknown>) => request<any>("POST", "/api/saved-queries", body),
  savedQueries: () => request<any[]>("GET", "/api/saved-queries"),
  resolutionCandidates: (decision?: string) => request<any>("GET", `/api/resolution/candidates${qs({ decision })}`),
  reviewCandidate: (id: string, decision: "CONFIRM" | "REJECT", note: string) =>
    request<any>("POST", `/api/resolution/candidates/${id}/review`, { decision, note }),
  audit: (p: Record<string, unknown> = {}) => request<any>("GET", `/api/audit${qs(p)}`),
  report: async (id: string, format: "pdf" | "markdown" | "json") => {
    const res = await request<Response>("GET", `/api/investigations/${id}/report?format=${format}`, undefined, { raw: true });
    return res.blob();
  },
  exportData: async (body: Record<string, unknown>) => {
    const res = await request<Response>("POST", "/api/export", body, { raw: true });
    return res.blob();
  },
};

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
