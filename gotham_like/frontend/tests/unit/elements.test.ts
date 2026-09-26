import { describe, expect, it } from "vitest";
import { normalise, toElements, truncate } from "../../src/graph/elements";
import type { Edge, EntitySummary } from "../../src/api/types";

const n = (id: string, type = "Account"): EntitySummary => ({ id, type, label: `label-${id}`, confidence: 1, epistemic_status: "DERIVED", lat: null, lon: null, observed_at: null });
const e = (id: string, s: string, t: string, type = "USED", extra: Partial<Edge> = {}): Edge => ({
  id, source: s, target: t, relationship_type: type, timestamp: null, confidence: 1, epistemic_status: "DERIVED", properties: {}, source_records: [], provenance: {}, ...extra,
});

describe("graph element conversion", () => {
  it("aggregates parallel edges of the same type with a count", () => {
    const els = toElements([n("a"), n("b")], [e("1", "a", "b"), e("2", "a", "b"), e("3", "a", "b", "OWNS")]);
    const edges = els.filter((x) => x.group === "edges");
    expect(edges).toHaveLength(2);
    expect(edges.find((x) => x.data.count === 2)?.data.label).toBe("USED ×2");
  });
  it("marks path edges and nodes, and verified status", () => {
    const els = toElements([n("a"), n("b")], [e("1", "a", "b", "USED", { epistemic_status: "VERIFIED" })], { path: ["1"] });
    expect(els.find((x) => x.data.id === "1")?.classes).toContain("onpath");
    expect(els.find((x) => x.data.id === "1")?.classes).toContain("VERIFIED");
    expect(els.find((x) => x.data.id === "a")?.classes).toContain("onpath");
  });
  it("sizes nodes by normalised analytic score", () => {
    const scores = normalise([{ id: "a", score: 0.5 }, { id: "b", score: 0.25 }]);
    expect(scores).toEqual({ a: 1, b: 0.5 });
    const els = toElements([n("a"), n("b")], [], { analytics: scores });
    expect(els.find((x) => x.data.id === "a")?.data.size).toBeGreaterThan(els.find((x) => x.data.id === "b")?.data.size as number);
  });
  it("drops edges to nodes not in view", () => {
    expect(toElements([n("a")], [e("1", "a", "zz")]).filter((x) => x.group === "edges")).toHaveLength(0);
  });
  it("truncates long labels", () => {
    expect(truncate("x".repeat(40), 10)).toHaveLength(10);
  });
});
