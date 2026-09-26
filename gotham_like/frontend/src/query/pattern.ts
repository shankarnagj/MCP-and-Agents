/** Pure helpers for the visual query builder (unit-tested). */
export interface QNode { var: string; type: string; filters: { property: string; op: string; value: string }[] }
export interface QEdge { from: string; to: string; type: string; time_from: string; time_to: string }
export interface QAgg { enabled: boolean; group_by: string; count_distinct: string; op: string; value: number }

export function buildPattern(nodes: QNode[], edges: QEdge[], agg: QAgg, limit = 100): Record<string, unknown> {
  const p: Record<string, unknown> = {
    nodes: nodes.map((n) => ({
      var: n.var, type: n.type,
      filters: n.filters.filter((f) => f.property && f.value !== "").map((f) => ({ property: f.property, op: f.op, value: coerce(f.value) })),
    })),
    edges: edges.map((e) => ({ from: e.from, to: e.to, type: e.type || null, time_from: e.time_from || null, time_to: e.time_to || null })),
    limit,
  };
  if (agg.enabled) p.aggregate = { group_by: agg.group_by, count_distinct: agg.count_distinct, op: agg.op, value: agg.value };
  return p;
}

function coerce(v: string): string | number {
  return /^-?\d+(\.\d+)?$/.test(v) ? Number(v) : v;
}

/** Human-readable rendering of the pattern (the "diagram" in the builder). */
export function describePattern(nodes: QNode[], edges: QEdge[]): string[] {
  const byVar = Object.fromEntries(nodes.map((n) => [n.var, n]));
  return edges.map((e) => `(${e.from}:${byVar[e.from]?.type ?? "?"}) -[${e.type || "*"}]-> (${e.to}:${byVar[e.to]?.type ?? "?"})`);
}

export const PRESETS: { name: string; nodes: QNode[]; edges: QEdge[]; agg: QAgg }[] = [
  {
    name: "Devices shared by > 3 persons (March 2026)",
    nodes: [{ var: "p", type: "Person", filters: [] }, { var: "a", type: "Account", filters: [] }, { var: "d", type: "Device", filters: [] }],
    edges: [{ from: "p", to: "a", type: "OWNS", time_from: "", time_to: "" }, { from: "a", to: "d", type: "USED", time_from: "2026-03-01", time_to: "2026-03-31" }],
    agg: { enabled: true, group_by: "d", count_distinct: "p", op: ">", value: 3 },
  },
  {
    name: "Large transfers into accounts owned by Castellan Isles companies",
    nodes: [{ var: "t", type: "Transaction", filters: [{ property: "amount", op: ">=", value: "9000" }] }, { var: "a", type: "Account", filters: [] },
            { var: "o", type: "Organization", filters: [{ property: "jurisdiction", op: "=", value: "Castellan Isles" }] }],
    edges: [{ from: "t", to: "a", type: "TRANSFERRED_TO", time_from: "", time_to: "" }, { from: "o", to: "a", type: "OWNS", time_from: "", time_to: "" }],
    agg: { enabled: false, group_by: "a", count_distinct: "t", op: ">", value: 1 },
  },
  {
    name: "Beneficial control chains (Person → Org → Org)",
    nodes: [{ var: "p", type: "Person", filters: [] }, { var: "o1", type: "Organization", filters: [] }, { var: "o2", type: "Organization", filters: [] }],
    edges: [{ from: "p", to: "o1", type: "CONTROLS", time_from: "", time_to: "" }, { from: "o1", to: "o2", type: "CONTROLS", time_from: "", time_to: "" }],
    agg: { enabled: false, group_by: "p", count_distinct: "o2", op: ">", value: 1 },
  },
];
