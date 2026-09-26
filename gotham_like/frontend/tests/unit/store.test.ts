import { describe, expect, it } from "vitest";
import { initialState, reducer, visibleEdges, visibleNodes } from "../../src/state/store";
import type { Edge, EntitySummary } from "../../src/api/types";

const node = (id: string, type = "Account"): EntitySummary => ({ id, type, label: id, confidence: 1, epistemic_status: "DERIVED", lat: null, lon: null, observed_at: null });
const edge = (id: string, s: string, t: string, extra: Partial<Edge> = {}): Edge => ({
  id, source: s, target: t, relationship_type: "USED", timestamp: "2026-03-01T00:00:00+00:00", confidence: 1, epistemic_status: "DERIVED",
  properties: {}, source_records: ["src_1"], provenance: {}, ...extra,
});

describe("workspace reducer", () => {
  it("adds nodes and only edges whose endpoints exist", () => {
    const s = reducer(initialState, { type: "ADD_GRAPH", nodes: [node("a"), node("b")], edges: [edge("e1", "a", "b"), edge("e2", "a", "zzz")] });
    expect(Object.keys(s.nodes)).toEqual(["a", "b"]);
    expect(Object.keys(s.edges)).toEqual(["e1"]);
  });

  it("removing a node removes its edges and clears selection", () => {
    let s = reducer(initialState, { type: "ADD_GRAPH", nodes: [node("a"), node("b")], edges: [edge("e1", "a", "b")] });
    s = reducer(s, { type: "SELECT", selection: { kind: "entity", id: "a" } });
    s = reducer(s, { type: "REMOVE_NODES", ids: ["a"] });
    expect(s.edges).toEqual({});
    expect(s.selection).toBeNull();
  });

  it("multi-select keeps at most two nodes (path endpoints)", () => {
    let s = initialState;
    for (const id of ["a", "b", "c"]) s = reducer(s, { type: "TOGGLE_MULTI", id });
    expect(s.multi).toEqual(["b", "c"]);
  });

  it("keeps a bounded recent-history list", () => {
    let s = initialState;
    for (let i = 0; i < 40; i++) s = reducer(s, { type: "SELECT", selection: { kind: "entity", id: `n${i}` } });
    expect(s.history.length).toBe(30);
    expect(s.history[0]).toBe("n39");
  });
});

describe("analytical filters", () => {
  const base = reducer(initialState, {
    type: "ADD_GRAPH",
    nodes: [node("a"), node("b", "Device"), node("c", "Location")],
    edges: [
      edge("e1", "a", "b"),
      edge("e2", "b", "c", { relationship_type: "VISITED", timestamp: "2026-05-01T00:00:00+00:00", confidence: 0.5 }),
      edge("e3", "a", "c", { relationship_type: "LOCATED_AT", epistemic_status: "SYSTEM_INFERENCE" }),
    ],
  });
  it("filters by relationship type", () => {
    const s = reducer(base, { type: "SET_FILTERS", filters: { relationshipTypes: ["USED"] } });
    expect(visibleEdges(s).map((e) => e.id)).toEqual(["e1"]);
  });
  it("filters by time window", () => {
    const s = reducer(base, { type: "SET_FILTERS", filters: { timeFrom: "2026-04-01T00:00:00+00:00" } });
    expect(visibleEdges(s).map((e) => e.id)).toEqual(["e2"]);
  });
  it("filters by confidence and epistemic status", () => {
    expect(visibleEdges(reducer(base, { type: "SET_FILTERS", filters: { minConfidence: 0.8 } })).map((e) => e.id)).toEqual(["e1", "e3"]);
    expect(visibleEdges(reducer(base, { type: "SET_FILTERS", filters: { epistemic: ["DERIVED"] } })).map((e) => e.id)).toEqual(["e1", "e2"]);
  });
  it("hiding an entity type hides its nodes and incident edges", () => {
    const s = reducer(base, { type: "SET_FILTERS", filters: { hiddenEntityTypes: ["Location"] } });
    expect(visibleNodes(s).map((n) => n.id)).toEqual(["a", "b"]);
    expect(visibleEdges(s).map((e) => e.id)).toEqual(["e1"]);
  });
});
