import { useState } from "react";
import { api } from "../api/client";
import { Button, Empty, PanelHeader, TypeDot } from "../components/ui";
import { TYPE_COLORS } from "../graph/elements";
import { useActions } from "../state/actions";
import { can, useStore } from "../state/context";
import { buildPattern, describePattern, PRESETS, type QAgg, type QEdge, type QNode } from "./pattern";

const OPS = ["=", "!=", ">", ">=", "<", "<=", "contains"];

export function QueryBuilder() {
  const { ontology, dispatch, me, state } = useStore();
  const { addEntity, fail } = useActions();
  const [nodes, setNodes] = useState<QNode[]>(PRESETS[0].nodes);
  const [edges, setEdges] = useState<QEdge[]>(PRESETS[0].edges);
  const [agg, setAgg] = useState<QAgg>(PRESETS[0].agg);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const etypes = Object.keys(ontology?.entity_types ?? {});
  const rtypes = Object.keys(ontology?.relationship_types ?? {});
  const vars = nodes.map((n) => n.var);
  const pattern = buildPattern(nodes, edges, agg);

  const run = async () => {
    setBusy(true);
    try { setRes(await api.query(pattern, true)); } catch (e) { fail(e); setRes(null); } finally { setBusy(false); }
  };
  const save = async () => {
    const name = prompt("Saved query name?");
    if (!name) return;
    try {
      await api.saveQuery({ name, query_kind: "pattern", query: pattern, parameters: {}, filters: {}, investigation_id: state.investigationId });
      dispatch({ type: "TOAST", level: "info", text: "Query saved" });
    } catch (e) { fail(e); }
  };
  const setNode = (i: number, patch: Partial<QNode>) => setNodes(nodes.map((n, j) => (i === j ? { ...n, ...patch } : n)));
  const setEdge = (i: number, patch: Partial<QEdge>) => setEdges(edges.map((e, j) => (i === j ? { ...e, ...patch } : e)));
  const sel = "h-6 rounded-sm border border-ink-600 bg-ink-950 px-1 text-2xs";

  return (
    <div className="grid h-full grid-cols-2 gap-px bg-ink-800">
      <div className="flex flex-col overflow-hidden bg-ink-900">
        <PanelHeader title="Visual query builder">
          <select className={sel} defaultValue="" aria-label="Preset" onChange={(e) => { const p = PRESETS[Number(e.target.value)]; if (p) { setNodes(p.nodes); setEdges(p.edges); setAgg(p.agg); setRes(null); } }}>
            <option value="">Presets…</option>
            {PRESETS.map((p, i) => <option key={p.name} value={i}>{p.name}</option>)}
          </select>
        </PanelHeader>
        <div className="flex-1 space-y-3 overflow-auto p-2 text-xs">
          <div>
            <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Nodes</div>
            {nodes.map((n, i) => (
              <div key={i} className="mb-1 rounded-sm border border-ink-700 p-1">
                <div className="flex items-center gap-1">
                  <input className={sel + " w-12 font-mono"} value={n.var} onChange={(e) => setNode(i, { var: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} aria-label="var" />
                  <TypeDot color={TYPE_COLORS[n.type] ?? "#999"} />
                  <select className={sel} value={n.type} onChange={(e) => setNode(i, { type: e.target.value, filters: [] })}>{etypes.map((t) => <option key={t}>{t}</option>)}</select>
                  <Button variant="ghost" onClick={() => setNode(i, { filters: [...n.filters, { property: "", op: "=", value: "" }] })}>+ filter</Button>
                  <Button variant="ghost" onClick={() => setNodes(nodes.filter((_, j) => j !== i))}>×</Button>
                </div>
                {n.filters.map((f, k) => (
                  <div key={k} className="ml-6 mt-1 flex gap-1">
                    <select className={sel} value={f.property} onChange={(e) => setNode(i, { filters: n.filters.map((x, m) => (m === k ? { ...x, property: e.target.value } : x)) })}>
                      <option value="">property…</option>
                      {Object.keys(ontology?.entity_types?.[n.type]?.properties ?? {}).map((p) => <option key={p}>{p}</option>)}
                    </select>
                    <select className={sel} value={f.op} onChange={(e) => setNode(i, { filters: n.filters.map((x, m) => (m === k ? { ...x, op: e.target.value } : x)) })}>{OPS.map((o) => <option key={o}>{o}</option>)}</select>
                    <input className={sel + " flex-1"} value={f.value} onChange={(e) => setNode(i, { filters: n.filters.map((x, m) => (m === k ? { ...x, value: e.target.value } : x)) })} />
                  </div>
                ))}
              </div>
            ))}
            <Button onClick={() => setNodes([...nodes, { var: `n${nodes.length}`, type: etypes[0] ?? "Person", filters: [] }])}>+ node</Button>
          </div>
          <div>
            <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Relationships</div>
            {edges.map((e, i) => (
              <div key={i} className="mb-1 flex flex-wrap items-center gap-1 rounded-sm border border-ink-700 p-1">
                <select className={sel} value={e.from} onChange={(ev) => setEdge(i, { from: ev.target.value })}>{vars.map((v) => <option key={v}>{v}</option>)}</select>
                <select className={sel} value={e.type} onChange={(ev) => setEdge(i, { type: ev.target.value })}><option value="">any</option>{rtypes.map((t) => <option key={t}>{t}</option>)}</select>
                <span>→</span>
                <select className={sel} value={e.to} onChange={(ev) => setEdge(i, { to: ev.target.value })}>{vars.map((v) => <option key={v}>{v}</option>)}</select>
                <input type="date" className={sel} value={e.time_from} onChange={(ev) => setEdge(i, { time_from: ev.target.value })} aria-label="from" />
                <input type="date" className={sel} value={e.time_to} onChange={(ev) => setEdge(i, { time_to: ev.target.value })} aria-label="to" />
                <Button variant="ghost" onClick={() => setEdges(edges.filter((_, j) => j !== i))}>×</Button>
              </div>
            ))}
            <Button onClick={() => setEdges([...edges, { from: vars[0], to: vars[1] ?? vars[0], type: "", time_from: "", time_to: "" }])}>+ relationship</Button>
          </div>
          <div>
            <label className="flex items-center gap-1 text-2xs uppercase tracking-wider text-ink-400">
              <input type="checkbox" checked={agg.enabled} onChange={(e) => setAgg({ ...agg, enabled: e.target.checked })} /> Aggregate
            </label>
            {agg.enabled && (
              <div className="mt-1 flex items-center gap-1">
                group by <select className={sel} value={agg.group_by} onChange={(e) => setAgg({ ...agg, group_by: e.target.value })}>{vars.map((v) => <option key={v}>{v}</option>)}</select>
                count distinct <select className={sel} value={agg.count_distinct} onChange={(e) => setAgg({ ...agg, count_distinct: e.target.value })}>{vars.map((v) => <option key={v}>{v}</option>)}</select>
                <select className={sel} value={agg.op} onChange={(e) => setAgg({ ...agg, op: e.target.value })}>{[">", ">=", "=", "<", "<="].map((o) => <option key={o}>{o}</option>)}</select>
                <input type="number" className={sel + " w-14"} value={agg.value} onChange={(e) => setAgg({ ...agg, value: Number(e.target.value) })} />
              </div>
            )}
          </div>
          <div className="rounded-sm border border-ink-700 bg-ink-950 p-2 font-mono text-2xs text-ink-300">
            {describePattern(nodes, edges).map((l) => <div key={l}>{l}</div>)}
          </div>
          <div className="flex gap-1">
            <Button variant="primary" disabled={busy} onClick={run}>Run query</Button>
            {can(me, "investigation:write") && <Button onClick={save}>Save query</Button>}
          </div>
        </div>
      </div>
      <div className="flex flex-col overflow-hidden bg-ink-900">
        <PanelHeader title={res ? `Results · ${res.row_count} row(s) · ${res.elapsed_ms} ms${res.truncated ? " · truncated" : ""}` : "Query plan & results"} />
        <div className="flex-1 overflow-auto p-2 text-xs">
          {!res && <Empty>Build a pattern and run it. The plan shows each step and the index it relies on.</Empty>}
          {res && (
            <>
              <div className="mb-2 text-2xs uppercase tracking-wider text-ink-400">Plan</div>
              <ol className="mb-3 list-decimal pl-5 font-mono text-2xs text-ink-300">
                {res.plan.map((s: any, i: number) => <li key={i}>{JSON.stringify(s)}</li>)}
              </ol>
              <div className="mb-2 text-2xs uppercase tracking-wider text-ink-400">Rows</div>
              {res.rows.map((r: any, i: number) => (
                <div key={i} className="mb-1 rounded-sm border border-ink-700 p-1">
                  {"group" in r ? (
                    <>
                      <div className="cursor-pointer font-semibold" onClick={() => addEntity(r.group)}>{res.entities[r.group]?.label ?? r.group} — {r.count} distinct</div>
                      <div className="flex flex-wrap gap-1">{r.members.map((m: string) => (
                        <button key={m} className="rounded-sm bg-ink-800 px-1 text-2xs" onClick={() => addEntity(m, false)}>{res.entities[m]?.label ?? m}</button>
                      ))}</div>
                    </>
                  ) : (
                    <div className="flex flex-wrap gap-2">{Object.entries(r).map(([k, v]) => (
                      <button key={k} className="text-2xs" onClick={() => addEntity(String(v), false)}><span className="text-ink-400">{k}:</span> {res.entities[String(v)]?.label ?? String(v)}</button>
                    ))}</div>
                  )}
                </div>
              ))}
              <details className="mt-2"><summary className="cursor-pointer text-2xs text-ink-400">SQL (parameterised)</summary><pre className="whitespace-pre-wrap font-mono text-2xs text-ink-400">{res.sql}</pre></details>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
