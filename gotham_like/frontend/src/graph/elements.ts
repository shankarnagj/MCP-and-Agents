import type { Edge, EntitySummary } from "../api/types";

export const TYPE_COLORS: Record<string, string> = {
  Person: "#6fb6ff", Organization: "#f0b35e", Account: "#9d8cff", Device: "#57d3c1", Transaction: "#8b98ad", Location: "#7fd46a",
  Address: "#a6c47a", IPAddress: "#e38b8b", Domain: "#e67fb8", Vehicle: "#c9a36a", Shipment: "#d6c35a", Vessel: "#4fc3e8",
  Event: "#b0b0b0", Document: "#cfcfcf", Case: "#ff9f6b",
};

export const TYPE_GLYPH: Record<string, string> = {
  Person: "P", Organization: "O", Account: "A", Device: "D", Transaction: "T", Location: "L", Address: "Ad", IPAddress: "IP",
  Domain: "Dn", Vehicle: "V", Shipment: "S", Vessel: "Vs", Event: "E", Document: "Doc", Case: "C",
};

export interface CyElement {
  group: "nodes" | "edges";
  data: Record<string, unknown>;
  classes?: string;
}

export function toElements(nodes: EntitySummary[], edges: Edge[], opts: { analytics?: Record<string, number> | null; path?: string[] | null; multi?: string[] } = {}): CyElement[] {
  const ids = new Set(nodes.map((n) => n.id));
  const pathSet = new Set(opts.path ?? []);
  const pathNodes = new Set<string>();
  edges.forEach((e) => {
    if (pathSet.has(e.id)) {
      pathNodes.add(e.source);
      pathNodes.add(e.target);
    }
  });
  const out: CyElement[] = nodes.map((n) => {
    const score = opts.analytics?.[n.id];
    const classes = [n.type, n.epistemic_status, opts.multi?.includes(n.id) ? "multi" : "", pathNodes.has(n.id) ? "onpath" : "", score !== undefined ? "scored" : ""]
      .filter(Boolean)
      .join(" ");
    return {
      group: "nodes",
      data: {
        id: n.id,
        label: truncate(n.label, 28),
        type: n.type,
        glyph: TYPE_GLYPH[n.type] ?? "?",
        color: TYPE_COLORS[n.type] ?? "#999",
        size: score !== undefined ? 22 + 38 * score : 26,
        confidence: n.confidence,
      },
      classes,
    };
  });
  // Parallel edges of the same type between the same pair are drawn once with a count
  // (e.g. 7 CONNECTED_TO observations) — the individual records remain in the table/provenance views.
  const groups = new Map<string, Edge[]>();
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    const k = `${e.source}|${e.target}|${e.relationship_type}`;
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(e);
  }
  for (const members of groups.values()) {
    const e = members.find((m) => pathSet.has(m.id)) ?? members[0];
    const onPath = members.some((m) => pathSet.has(m.id));
    const minConf = Math.min(...members.map((m) => m.confidence));
    const status = members.some((m) => m.epistemic_status === "VERIFIED") ? "VERIFIED" : e.epistemic_status;
    out.push({
      group: "edges",
      data: { id: e.id, source: e.source, target: e.target, label: members.length > 1 ? `${e.relationship_type} ×${members.length}` : e.relationship_type,
              confidence: minConf, ts: e.timestamp, count: members.length, members: members.map((m) => m.id), width: Math.min(1 + Math.log2(members.length), 5) },
      classes: [status, onPath ? "onpath" : "", minConf < 0.8 ? "lowconf" : ""].filter(Boolean).join(" "),
    });
  }
  return out;
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/** Normalise analytic scores to 0..1 for sizing. */
export function normalise(top: { id: string; score: number }[]): Record<string, number> {
  if (!top.length) return {};
  const max = Math.max(...top.map((t) => t.score)) || 1;
  return Object.fromEntries(top.map((t) => [t.id, t.score / max]));
}
