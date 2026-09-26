import type { Alert, Edge, EntitySummary } from "../api/types";

export type Mode = "graph" | "map" | "timeline" | "table" | "entity" | "investigation" | "query";
export type Selection =
  | { kind: "entity"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "event"; id: string }
  | { kind: "signal"; id: string }
  | null;

export interface Filters {
  relationshipTypes: string[] | null; // null = all
  hiddenEntityTypes: string[];
  timeFrom: string | null;
  timeTo: string | null;
  minConfidence: number;
  epistemic: string[] | null;
}

export interface Toast {
  id: number;
  level: "info" | "error" | "signal";
  text: string;
}

export interface State {
  nodes: Record<string, EntitySummary>;
  edges: Record<string, Edge>;
  selection: Selection;
  multi: string[]; // multi-selected node ids (for path finding)
  mode: Mode;
  filters: Filters;
  investigationId: string | null;
  alerts: Alert[];
  toasts: Toast[];
  analytics: Record<string, number> | null; // node id -> normalised analytic score (ANALYTICAL SIGNAL overlay)
  highlightPath: string[] | null; // edge ids
  history: string[]; // recently viewed entity ids
}

export const initialFilters: Filters = { relationshipTypes: null, hiddenEntityTypes: [], timeFrom: null, timeTo: null, minConfidence: 0, epistemic: null };

export const initialState: State = {
  nodes: {},
  edges: {},
  selection: null,
  multi: [],
  mode: "graph",
  filters: initialFilters,
  investigationId: null,
  alerts: [],
  toasts: [],
  analytics: null,
  highlightPath: null,
  history: [],
};

export type Action =
  | { type: "ADD_GRAPH"; nodes: EntitySummary[]; edges: Edge[] }
  | { type: "REMOVE_NODES"; ids: string[] }
  | { type: "CLEAR" }
  | { type: "SELECT"; selection: Selection }
  | { type: "TOGGLE_MULTI"; id: string }
  | { type: "SET_MODE"; mode: Mode }
  | { type: "SET_FILTERS"; filters: Partial<Filters> }
  | { type: "SET_INVESTIGATION"; id: string | null }
  | { type: "SET_ALERTS"; alerts: Alert[] }
  | { type: "PUSH_ALERT"; alert: Alert }
  | { type: "TOAST"; level: Toast["level"]; text: string }
  | { type: "DISMISS_TOAST"; id: number }
  | { type: "SET_ANALYTICS"; scores: Record<string, number> | null }
  | { type: "HIGHLIGHT_PATH"; edgeIds: string[] | null };

let toastSeq = 0;

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ADD_GRAPH": {
      const nodes = { ...state.nodes };
      for (const n of action.nodes) nodes[n.id] = { ...nodes[n.id], ...n };
      const edges = { ...state.edges };
      for (const e of action.edges) if (nodes[e.source] && nodes[e.target]) edges[e.id] = e;
      return { ...state, nodes, edges };
    }
    case "REMOVE_NODES": {
      const drop = new Set(action.ids);
      const nodes = Object.fromEntries(Object.entries(state.nodes).filter(([id]) => !drop.has(id)));
      const edges = Object.fromEntries(Object.entries(state.edges).filter(([, e]) => !drop.has(e.source) && !drop.has(e.target)));
      const selection = state.selection?.kind === "entity" && drop.has(state.selection.id) ? null : state.selection;
      return { ...state, nodes, edges, selection, multi: state.multi.filter((m) => !drop.has(m)) };
    }
    case "CLEAR":
      return { ...state, nodes: {}, edges: {}, selection: null, multi: [], analytics: null, highlightPath: null };
    case "SELECT": {
      const history =
        action.selection?.kind === "entity" ? [action.selection.id, ...state.history.filter((h) => h !== action.selection!.id)].slice(0, 30) : state.history;
      return { ...state, selection: action.selection, history };
    }
    case "TOGGLE_MULTI": {
      const has = state.multi.includes(action.id);
      const multi = has ? state.multi.filter((m) => m !== action.id) : [...state.multi, action.id].slice(-2);
      return { ...state, multi };
    }
    case "SET_MODE":
      return { ...state, mode: action.mode };
    case "SET_FILTERS":
      return { ...state, filters: { ...state.filters, ...action.filters } };
    case "SET_INVESTIGATION":
      return { ...state, investigationId: action.id };
    case "SET_ALERTS":
      return { ...state, alerts: action.alerts };
    case "PUSH_ALERT":
      return { ...state, alerts: [action.alert, ...state.alerts.filter((a) => a.id !== action.alert.id)].slice(0, 500) };
    case "TOAST":
      return { ...state, toasts: [...state.toasts, { id: ++toastSeq, level: action.level, text: action.text }].slice(-5) };
    case "DISMISS_TOAST":
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) };
    case "SET_ANALYTICS":
      return { ...state, analytics: action.scores };
    case "HIGHLIGHT_PATH":
      return { ...state, highlightPath: action.edgeIds };
    default:
      return state;
  }
}

/** Visible edges after applying analytical filters (pure; used by graph, map and tables). */
export function visibleEdges(state: Pick<State, "edges" | "nodes" | "filters">): Edge[] {
  const f = state.filters;
  const hidden = new Set(f.hiddenEntityTypes);
  return Object.values(state.edges).filter((e) => {
    const s = state.nodes[e.source];
    const t = state.nodes[e.target];
    if (!s || !t || hidden.has(s.type) || hidden.has(t.type)) return false;
    if (f.relationshipTypes && !f.relationshipTypes.includes(e.relationship_type)) return false;
    if (e.confidence < f.minConfidence) return false;
    if (f.epistemic && !f.epistemic.includes(e.epistemic_status)) return false;
    if (e.timestamp) {
      if (f.timeFrom && e.timestamp < f.timeFrom) return false;
      if (f.timeTo && e.timestamp > f.timeTo) return false;
    }
    return true;
  });
}

export function visibleNodes(state: Pick<State, "nodes" | "filters">): EntitySummary[] {
  const hidden = new Set(state.filters.hiddenEntityTypes);
  return Object.values(state.nodes).filter((n) => !hidden.has(n.type));
}
