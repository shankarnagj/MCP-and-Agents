/** Client-side tokenizer for the search language (highlighting + hints). Mirrors backend app/search/parser.py. */

export const FIELD_ALIASES = [
  "account", "device", "ip", "email", "phone", "domain", "txn", "shipment", "imo", "plate", "reg", "id",
  "company", "org", "person", "location", "vessel", "type", "after", "before", "on", "near", "bbox",
] as const;

export type TokenKind = "identifier" | "type" | "date" | "geo" | "phrase" | "prefix" | "fuzzy" | "property" | "negation";

export interface Token {
  text: string;
  kind: TokenKind;
  field?: string;
  value?: string;
}

const IDENT = new Set(["account", "acct", "device", "ip", "email", "phone", "domain", "txn", "transaction", "shipment", "imo", "plate", "reg", "id"]);
const TYPED = new Set(["company", "org", "organization", "person", "location", "vessel", "place", "type"]);
const DATE = new Set(["after", "before", "on", "from", "to", "since", "until"]);
const GEO = new Set(["near", "bbox"]);

export function tokenize(q: string): Token[] {
  const out: Token[] = [];
  const re = /(-?[\w.]+:"[^"]*"|"[^"]*"|\S+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(q))) {
    const raw = m[1];
    if (raw.startsWith('"')) {
      out.push({ text: raw, kind: "phrase", value: raw.slice(1, -1) });
      continue;
    }
    const neg = raw.startsWith("-") && raw.includes(":");
    const body = neg ? raw.slice(1) : raw;
    const idx = body.indexOf(":");
    if (idx > 0 && idx < body.length - 1) {
      const field = body.slice(0, idx).toLowerCase();
      const value = body.slice(idx + 1).replace(/^"|"$/g, "");
      let kind: TokenKind = "property";
      if (neg) kind = "negation";
      else if (IDENT.has(field)) kind = "identifier";
      else if (TYPED.has(field)) kind = "type";
      else if (DATE.has(field)) kind = "date";
      else if (GEO.has(field)) kind = "geo";
      out.push({ text: raw, kind, field, value });
      continue;
    }
    if (raw.endsWith("*") && raw.length > 1) out.push({ text: raw, kind: "prefix", value: raw.slice(0, -1) });
    else out.push({ text: raw, kind: "fuzzy", value: raw.replace(/^~/, "") });
  }
  return out;
}

export function suggestFields(partial: string): string[] {
  const p = partial.toLowerCase();
  if (!p || p.includes(":")) return [];
  return FIELD_ALIASES.filter((f) => f.startsWith(p) && f !== p).map((f) => `${f}:`);
}

export const EXAMPLES = [
  'device:DV-7F3A-SHARED',
  'ip:203.0.113.66',
  'company:Northwind',
  'account:ACC-9000001',
  '"Harbor Plaza"',
  'type:Transaction near:51.45,3.60,2km on:2026-02-14',
  'jurisdiction:"Castellan Isles"',
  'Zusil*',
];
