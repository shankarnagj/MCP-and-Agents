import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SearchResponse } from "../api/types";
import { TYPE_COLORS } from "../graph/elements";
import { useStore } from "../state/context";
import { useActions } from "../state/actions";
import { cx, TypeDot } from "../components/ui";
import { EXAMPLES, suggestFields, tokenize, type TokenKind } from "./syntax";

const KIND_COLOR: Record<TokenKind, string> = {
  identifier: "text-accent", type: "text-[#f0b35e]", date: "text-[#7fd46a]", geo: "text-[#57d3c1]", phrase: "text-ink-100",
  prefix: "text-ink-200", fuzzy: "text-ink-200", property: "text-hypo", negation: "text-danger",
};

export function CommandBar() {
  const { dispatch, me } = useStore();
  const { addEntity, expand } = useActions();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = async (query = q) => {
    if (!query.trim()) return;
    if (query.startsWith(">")) return command(query.slice(1).trim());
    setErr(null);
    try {
      const r = await api.search(query, 30);
      setRes(r);
      setCursor(0);
      setOpen(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRes(null);
    }
  };

  const command = (c: string) => {
    const [cmd] = c.split(/\s+/);
    const modes = ["graph", "map", "timeline", "table", "entity", "investigation", "query"];
    if (modes.includes(cmd)) dispatch({ type: "SET_MODE", mode: cmd as any });
    else if (cmd === "clear") dispatch({ type: "CLEAR" });
    else dispatch({ type: "TOAST", level: "info", text: `Commands: >${modes.join(" >")} >clear` });
    setQ("");
    setOpen(false);
  };

  const choose = async (i: number, withNeighbours = false) => {
    const r = res?.results[i];
    if (!r) return;
    await addEntity(r.id);
    if (withNeighbours) await expand([r.id], 1);
    setOpen(false);
  };

  const tokens = tokenize(q);
  const lastWord = q.split(/\s+/).pop() ?? "";
  const hints = suggestFields(lastWord);

  return (
    <div className="relative flex h-10 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-900 px-3">
      <div className="flex items-center gap-2 pr-2">
        <div className="h-4 w-4 rotate-45 border-2 border-accent" />
        <span className="text-sm font-semibold tracking-wide text-ink-100">TESSERA</span>
      </div>
      <div className="relative flex-1">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              if (open && res && res.results.length && res.query === q) choose(cursor, e.shiftKey);
              else run();
            } else if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, (res?.results.length ?? 1) - 1));
            else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
            else if (e.key === "Escape") setOpen(false);
          }}
          placeholder='Search or command (Ctrl+K) — e.g. device:DV-7F3A-SHARED · "Harbor Plaza" · company:Northwind · type:Transaction near:51.45,3.60,2km'
          aria-label="Global search"
          className="h-7 w-full rounded-sm border border-ink-600 bg-ink-950 px-2 font-mono text-xs text-ink-100 placeholder:text-ink-500 focus:border-accent focus:outline-none"
        />
        {q && (
          <div className="pointer-events-none absolute right-2 top-1 flex gap-1">
            {tokens.map((t, i) => (
              <span key={i} className={cx("rounded-sm bg-ink-800 px-1 font-mono text-2xs", KIND_COLOR[t.kind])} title={t.kind}>
                {t.kind}
              </span>
            ))}
          </div>
        )}
        {open && (res || err || hints.length > 0 || !q) && (
          <div className="absolute left-0 right-0 top-8 z-50 max-h-[70vh] overflow-auto rounded-sm border border-ink-600 bg-ink-900 shadow-2xl">
            {hints.length > 0 && (
              <div className="flex flex-wrap gap-1 border-b border-ink-700 p-2">
                {hints.map((h) => (
                  <button key={h} className="rounded-sm bg-ink-800 px-1 font-mono text-2xs text-accent" onClick={() => setQ(q.slice(0, q.length - lastWord.length) + h)}>
                    {h}
                  </button>
                ))}
              </div>
            )}
            {!q && (
              <div className="p-2">
                <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Examples</div>
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="block w-full px-1 py-[2px] text-left font-mono text-xs text-ink-200 hover:bg-ink-800" onClick={() => { setQ(ex); run(ex); }}>
                    {ex}
                  </button>
                ))}
              </div>
            )}
            {err && <div className="p-2 text-xs text-danger">{err}</div>}
            {res && (
              <>
                <div className="flex items-center gap-2 border-b border-ink-700 px-2 py-1 text-2xs text-ink-400">
                  <span>{res.total_estimate} match(es)</span>
                  {Object.entries(res.facets.type).map(([t, n]) => (
                    <span key={t} className="flex items-center gap-1"><TypeDot color={TYPE_COLORS[t] ?? "#999"} />{t} {n}</span>
                  ))}
                  <span className="ml-auto">Enter: add · Shift+Enter: add + 1-hop</span>
                </div>
                {res.parsed.warnings?.map((w) => <div key={w} className="px-2 py-1 text-2xs text-signal">{w}</div>)}
                {res.results.map((r, i) => (
                  <div
                    key={r.id}
                    onMouseEnter={() => setCursor(i)}
                    onClick={(e) => choose(i, e.shiftKey)}
                    className={cx("flex cursor-pointer items-center gap-2 px-2 py-1", i === cursor && "bg-ink-800")}
                  >
                    <TypeDot color={TYPE_COLORS[r.type] ?? "#999"} />
                    <span className="w-24 shrink-0 text-2xs text-ink-400">{r.type}</span>
                    <span className="truncate text-xs text-ink-100">{r.label}</span>
                    <span className="ml-auto truncate font-mono text-2xs text-ink-500">
                      {Object.entries(r.preview ?? {}).slice(0, 3).map(([k, v]) => `${k}=${String(v)}`).join(" · ")}
                    </span>
                    <span className="w-10 text-right font-mono text-2xs text-ink-400" title="retrieval similarity (not identity confidence)">{r.score?.toFixed(2)}</span>
                  </div>
                ))}
                <div className="border-t border-ink-700 px-2 py-1 text-2xs text-ink-500">{res.match_reasons.join(" · ")} — {res.note}</div>
              </>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 text-2xs text-ink-400">
        <span className="rounded-sm border border-signal/50 px-1 text-signal">SYNTHETIC / DEMONSTRATION DATA</span>
        <span className="font-mono">{me.username}</span>
        <span className="rounded-sm bg-ink-700 px-1">{me.role}</span>
      </div>
      {open && <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} style={{ top: 40 }} />}
    </div>
  );
}
