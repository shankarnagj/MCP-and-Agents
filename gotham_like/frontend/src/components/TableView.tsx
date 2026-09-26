import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Edge } from "../api/types";
import { TYPE_COLORS } from "../graph/elements";
import { useActions } from "../state/actions";
import { useStore } from "../state/context";
import { visibleEdges, visibleNodes } from "../state/store";
import { Button, cx, Empty, fmtPct, fmtTime, StatusBadge, Tabs, TypeDot } from "./ui";

type SortKey = "type" | "label" | "confidence" | "epistemic_status";

export function TableView() {
  const { state, dispatch } = useStore();
  const [tab, setTab] = useState<"entities" | "relationships">("entities");
  const [sort, setSort] = useState<SortKey>("type");
  const nodes = useMemo(() => [...visibleNodes(state)].sort((a, b) => String(a[sort]).localeCompare(String(b[sort]))), [state.nodes, state.filters, sort]);
  const edges = useMemo(() => visibleEdges(state), [state.edges, state.nodes, state.filters]);
  const H = ({ k, children }: { k: SortKey; children: string }) => (
    <th className="cursor-pointer px-2 text-left hover:text-ink-100" onClick={() => setSort(k)}>{children}{sort === k ? " ▾" : ""}</th>
  );
  return (
    <div className="flex h-full flex-col">
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "entities", label: `Entities (${nodes.length})` }, { id: "relationships", label: `Relationships (${edges.length})` }]} />
      <div className="flex-1 overflow-auto">
        {tab === "entities" && (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-ink-850 text-2xs uppercase text-ink-400">
              <tr><H k="type">Type</H><H k="label">Label</H><H k="confidence">Confidence</H><H k="epistemic_status">Status</H><th className="text-left">Observed</th><th className="text-left">Location</th></tr>
            </thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={n.id} className={cx("cursor-pointer border-b border-ink-800 hover:bg-ink-800", state.selection?.kind === "entity" && state.selection.id === n.id && "bg-ink-800")}
                  onClick={() => dispatch({ type: "SELECT", selection: { kind: "entity", id: n.id } })}>
                  <td className="px-2"><span className="flex items-center gap-1"><TypeDot color={TYPE_COLORS[n.type] ?? "#999"} />{n.type}</span></td>
                  <td>{n.label}</td><td className="font-mono">{fmtPct(n.confidence)}</td><td><StatusBadge status={n.epistemic_status} /></td>
                  <td className="font-mono text-2xs">{fmtTime(n.observed_at)}</td>
                  <td className="font-mono text-2xs text-ink-400">{n.lat != null ? `${n.lat.toFixed(4)}, ${n.lon!.toFixed(4)}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "relationships" && <EdgeTable edges={edges} />}
        {!nodes.length && <Empty>Workspace is empty.</Empty>}
      </div>
    </div>
  );
}

function EdgeTable({ edges }: { edges: Edge[] }) {
  const { state, dispatch } = useStore();
  const label = (id: string) => state.nodes[id]?.label ?? id;
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-ink-850 text-2xs uppercase text-ink-400">
        <tr><th className="px-2 text-left">Source</th><th className="text-left">Relationship</th><th className="text-left">Target</th><th className="text-left">Time</th><th className="text-left">Conf.</th><th className="text-left">Status</th><th className="text-left">Records</th></tr>
      </thead>
      <tbody>
        {edges.map((e) => (
          <tr key={e.id} className="cursor-pointer border-b border-ink-800 hover:bg-ink-800" onClick={() => dispatch({ type: "SELECT", selection: { kind: "edge", id: e.id } })}>
            <td className="px-2">{label(e.source)}</td><td className="font-mono text-2xs">{e.relationship_type}</td><td>{label(e.target)}</td>
            <td className="font-mono text-2xs">{fmtTime(e.timestamp)}</td><td className="font-mono">{fmtPct(e.confidence)}</td>
            <td><StatusBadge status={e.epistemic_status} /></td><td className="font-mono text-2xs text-ink-400">{e.source_records.length}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function EntityProfile() {
  const { state, dispatch } = useStore();
  const { expand, fail } = useActions();
  const id = state.selection?.kind === "entity" ? state.selection.id : null;
  const [rels, setRels] = useState<{ items: any[]; total: number; by_type: Record<string, number> } | null>(null);
  const [relType, setRelType] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    if (!id) return;
    api.relationships(id, { relationship_type: relType ?? undefined, limit: 100, offset }).then(setRels).catch(fail);
  }, [id, relType, offset, fail]);
  if (!id) return <Empty>Select an entity to open its profile.</Empty>;
  const node = state.nodes[id];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-ink-800 bg-ink-900 p-2">
        <TypeDot color={TYPE_COLORS[node?.type ?? ""] ?? "#999"} />
        <span className="text-sm font-semibold">{node?.label ?? id}</span>
        <span className="text-2xs text-ink-400">{node?.type}</span>
        <div className="ml-auto flex gap-1">
          <Button onClick={() => expand([id], 1)}>Expand in graph</Button>
        </div>
      </div>
      <div className="flex gap-1 border-b border-ink-800 p-2">
        <Button variant={relType === null ? "primary" : "default"} onClick={() => { setRelType(null); setOffset(0); }}>All {rels ? Object.values(rels.by_type).reduce((a, b) => a + b, 0) : ""}</Button>
        {rels && Object.entries(rels.by_type).map(([t, n]) => (
          <Button key={t} variant={relType === t ? "primary" : "default"} onClick={() => { setRelType(t); setOffset(0); }}>{t} {n}</Button>
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-ink-850 text-2xs uppercase text-ink-400">
            <tr><th className="px-2 text-left">Dir</th><th className="text-left">Relationship</th><th className="text-left">Other entity</th><th className="text-left">Time</th><th className="text-left">Status</th><th /></tr>
          </thead>
          <tbody>
            {rels?.items.map((r) => (
              <tr key={r.id} className="border-b border-ink-800 hover:bg-ink-800">
                <td className="px-2 font-mono text-2xs">{r.source === id ? "→" : "←"}</td>
                <td className="cursor-pointer font-mono text-2xs" onClick={() => dispatch({ type: "SELECT", selection: { kind: "edge", id: r.id } })}>{r.relationship_type}</td>
                <td>{r.other && <span className="flex items-center gap-1"><TypeDot color={TYPE_COLORS[r.other.type] ?? "#999"} />{r.other.label}</span>}</td>
                <td className="font-mono text-2xs">{fmtTime(r.timestamp)}</td>
                <td><StatusBadge status={r.epistemic_status} /></td>
                <td>{r.other && (
                  <Button variant="ghost" onClick={() => dispatch({ type: "ADD_GRAPH", nodes: [r.other, ...(state.nodes[id] ? [state.nodes[id]] : [])], edges: [r] })}>+ graph</Button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rels && rels.total > offset + 100 && (
          <div className="flex gap-1 p-2"><Button onClick={() => setOffset(offset + 100)}>Next 100 of {rels.total}</Button></div>
        )}
        {offset > 0 && <div className="p-2"><Button onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</Button></div>}
      </div>
    </div>
  );
}
