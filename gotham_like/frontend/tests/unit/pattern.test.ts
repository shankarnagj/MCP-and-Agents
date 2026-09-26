import { describe, expect, it } from "vitest";
import { buildPattern, describePattern, PRESETS } from "../../src/query/pattern";

describe("query builder pattern", () => {
  it("builds a backend pattern with aggregate and numeric coercion", () => {
    const p = PRESETS[1];
    const out = buildPattern(p.nodes, p.edges, p.agg) as any;
    expect(out.nodes[0].filters[0]).toEqual({ property: "amount", op: ">=", value: 9000 });
    expect(out.aggregate).toBeUndefined();
    const withAgg = buildPattern(PRESETS[0].nodes, PRESETS[0].edges, PRESETS[0].agg) as any;
    expect(withAgg.aggregate).toEqual({ group_by: "d", count_distinct: "p", op: ">", value: 3 });
    expect(withAgg.edges[1]).toMatchObject({ type: "USED", time_from: "2026-03-01" });
  });
  it("drops incomplete filters and renders a readable pattern", () => {
    const out = buildPattern([{ var: "a", type: "Account", filters: [{ property: "", op: "=", value: "x" }] }], [], { enabled: false, group_by: "a", count_distinct: "a", op: ">", value: 1 }) as any;
    expect(out.nodes[0].filters).toEqual([]);
    expect(describePattern(PRESETS[0].nodes, PRESETS[0].edges)[0]).toBe("(p:Person) -[OWNS]-> (a:Account)");
  });
});
