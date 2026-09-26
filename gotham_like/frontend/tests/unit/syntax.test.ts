import { describe, expect, it } from "vitest";
import { suggestFields, tokenize } from "../../src/search/syntax";

describe("search syntax tokenizer", () => {
  it("classifies identifiers, types, dates, geo, phrases, prefixes", () => {
    const t = tokenize('account:12345 company:Acme "John Smith" Joh* after:2026-01-01 near:51.4,3.6,2km -type:Transaction city:Marisk');
    expect(t.map((x) => x.kind)).toEqual(["identifier", "type", "phrase", "prefix", "date", "geo", "negation", "property"]);
    expect(t[0]).toMatchObject({ field: "account", value: "12345" });
    expect(t[2].value).toBe("John Smith");
  });
  it("handles quoted field values", () => {
    const t = tokenize('jurisdiction:"Castellan Isles"');
    expect(t).toHaveLength(1);
    expect(t[0]).toMatchObject({ kind: "property", field: "jurisdiction", value: "Castellan Isles" });
  });
  it("suggests field prefixes", () => {
    expect(suggestFields("dev")).toEqual(["device:"]);
    expect(suggestFields("ip:1")).toEqual([]);
  });
});
