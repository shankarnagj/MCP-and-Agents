import cytoscape, { type Core } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { Button, SignalTag } from "../components/ui";
import { useActions } from "../state/actions";
import { useStore } from "../state/context";
import { visibleEdges, visibleNodes } from "../state/store";
import { normalise, toElements, TYPE_COLORS } from "./elements";

const STYLE: any[] = [
  {
    selector: "node",
    style: {
      "background-color": "data(color)", width: "data(size)", height: "data(size)", label: "data(label)", color: "#c4ccd8", "font-size": 8,
      "text-valign": "bottom", "text-margin-y": 3, "text-outline-color": "#0b0e13", "text-outline-width": 2, "border-width": 1, "border-color": "#0b0e13",
    },
  },
  { selector: "node.Transaction", style: { shape: "round-rectangle", width: 14, height: 14 } },
  { selector: "node.Location", style: { shape: "diamond" } },
  { selector: "node.Organization", style: { shape: "hexagon" } },
  { selector: "node.Device", style: { shape: "round-tag" } },
  { selector: "node.IPAddress", style: { shape: "triangle" } },
  { selector: "node:selected", style: { "border-width": 3, "border-color": "#4ea1ff" } },
  { selector: "node.multi", style: { "border-width": 3, "border-color": "#b48cff" } },
  { selector: "node.onpath", style: { "border-width": 3, "border-color": "#e0a341" } },
  { selector: "node.scored", style: { "border-width": 2, "border-color": "#e0a341", "border-style": "dashed" } },
  {
    selector: "edge",
    style: {
      width: "data(width)", "line-color": "#3a4557", "min-zoomed-font-size": 9, "target-arrow-color": "#3a4557", "target-arrow-shape": "triangle", "arrow-scale": 0.6, "curve-style": "bezier",
      label: "data(label)", "font-size": 6, color: "#6f7b8f", "text-rotation": "autorotate", "text-background-color": "#0b0e13", "text-background-opacity": 0.8,
    },
  },
  { selector: "edge.VERIFIED", style: { "line-color": "#43c59e", "target-arrow-color": "#43c59e", width: 2 } },
  { selector: "edge.SYSTEM_INFERENCE", style: { "line-style": "dashed", "line-color": "#e0a341" } },
  { selector: "edge.ANALYST_ASSERTION", style: { "line-style": "dotted", "line-color": "#b48cff" } },
  { selector: "edge.lowconf", style: { opacity: 0.5 } },
  { selector: "edge.onpath", style: { "line-color": "#e0a341", "target-arrow-color": "#e0a341", width: 3 } },
  { selector: "edge:selected", style: { "line-color": "#4ea1ff", "target-arrow-color": "#4ea1ff", width: 3 } },
];

export function GraphView() {
  const { state, dispatch } = useStore();
  const { expand, fail } = useActions();
  const ref = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [layout, setLayout] = useState<"cose" | "concentric" | "breadthfirst" | "circle">("cose");
  const [busy, setBusy] = useState(false);
  const [analyticNote, setAnalyticNote] = useState<string | null>(null);

  const nodes = useMemo(() => visibleNodes(state), [state.nodes, state.filters]);
  const edges = useMemo(() => visibleEdges(state), [state.edges, state.nodes, state.filters]);

  useEffect(() => {
    if (!ref.current) return;
    const c = cytoscape({ container: ref.current, style: STYLE, wheelSensitivity: 0.25, minZoom: 0.05, maxZoom: 4, boxSelectionEnabled: true });
    cy.current = c;
    return () => c.destroy();
  }, []);

  // event handlers depend on current dispatch/expand
  useEffect(() => {
    const c = cy.current;
    if (!c) return;
    c.removeAllListeners();
    c.on("tap", "node", (e) => {
      const id = e.target.id();
      if ((e.originalEvent as MouseEvent).shiftKey) dispatch({ type: "TOGGLE_MULTI", id });
      else dispatch({ type: "SELECT", selection: { kind: "entity", id } });
    });
    c.on("dbltap", "node", (e) => expand([e.target.id()], 1));
    c.on("tap", "edge", (e) => dispatch({ type: "SELECT", selection: { kind: "edge", id: e.target.id() } }));
  }, [dispatch, expand]);

  useEffect(() => {
    const c = cy.current;
    if (!c) return;
    const els = toElements(nodes, edges, { analytics: state.analytics, path: state.highlightPath, multi: state.multi });
    const existing = new Set(c.elements().map((e) => e.id()));
    const incoming = new Set(els.map((e) => String(e.data.id)));
    c.batch(() => {
      c.elements().filter((e) => !incoming.has(e.id())).remove();
      for (const el of els) {
        const id = String(el.data.id);
        if (existing.has(id)) {
          const cur = c.getElementById(id);
          cur.data(el.data);
          cur.classes(el.classes ?? "");
        } else c.add(el as any);
      }
    });
    const added = els.some((e) => !existing.has(String(e.data.id)));
    if (added) c.layout({ name: layout, animate: false, fit: true, padding: 30, nodeRepulsion: () => 9000, idealEdgeLength: () => 70 } as any).run();
  }, [nodes, edges, state.analytics, state.highlightPath, state.multi, layout]);

  useEffect(() => {
    const c = cy.current;
    if (!c) return;
    c.elements().unselect();
    if (state.selection && (state.selection.kind === "entity" || state.selection.kind === "edge")) c.getElementById(state.selection.id).select();
  }, [state.selection]);

  const relayout = (name: typeof layout) => {
    setLayout(name);
    cy.current?.layout({ name, animate: false, fit: true, padding: 30 } as any).run();
  };

  const findPath = async (constrained: boolean) => {
    if (state.multi.length !== 2) return;
    setBusy(true);
    try {
      const [source, target] = state.multi;
      const res = await api.path({
        source, target, mode: "shortest", max_depth: 6,
        relationship_types: constrained ? ["OWNS", "USED", "INITIATED", "TRANSFERRED_TO", "CONTROLS", "WORKS_FOR", "CONNECTED_TO"] : null,
      });
      if (!res.found) {
        dispatch({ type: "TOAST", level: "info", text: `No path within ${res.search.max_depth} hops${res.search.truncated ? " (search truncated — not evidence of no connection)" : ""}` });
        return;
      }
      const p = res.paths[0];
      const nodesAdd = p.nodes.map((id: string) => res.entities[id]).filter(Boolean);
      const edgesAdd = p.steps.map((s: any) => ({
        id: s.edge_id, source: s.direction === "forward" ? s.from : s.to, target: s.direction === "forward" ? s.to : s.from,
        relationship_type: s.relationship_type, timestamp: s.timestamp, confidence: s.confidence, epistemic_status: s.epistemic_status,
        properties: {}, source_records: s.source_records, provenance: s.provenance,
      }));
      dispatch({ type: "ADD_GRAPH", nodes: nodesAdd, edges: edgesAdd });
      dispatch({ type: "HIGHLIGHT_PATH", edgeIds: edgesAdd.map((e: any) => e.id) });
      dispatch({ type: "TOAST", level: "info", text: `Path of length ${p.length} (min confidence ${p.min_confidence.toFixed(2)}). A path shows connectivity, not intent.` });
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const runAnalytics = async (alg: string) => {
    const seeds = Object.keys(state.nodes).slice(0, 200);
    if (!seeds.length) return;
    setBusy(true);
    try {
      const res = await api.analytics(seeds, [alg], 1);
      const r = res.results[alg];
      dispatch({ type: "SET_ANALYTICS", scores: normalise(r?.top ?? []) });
      setAnalyticNote(`${alg} — ${r?.method ?? ""} on ${res.window.nodes} nodes / ${res.window.edges} edges`);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const typeCounts = nodes.reduce<Record<string, number>>((acc, n) => ((acc[n.type] = (acc[n.type] ?? 0) + 1), acc), {});

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex h-8 shrink-0 items-center gap-1 border-b border-ink-800 bg-ink-900 px-2">
        <select className="h-6 rounded-sm border border-ink-600 bg-ink-850 px-1 text-2xs" value={layout} onChange={(e) => relayout(e.target.value as any)} aria-label="Layout">
          <option value="cose">force</option><option value="concentric">concentric</option><option value="breadthfirst">hierarchy</option><option value="circle">circle</option>
        </select>
        <Button onClick={() => { const sel = cy.current?.$("node:selected").map((n) => n.id()) ?? []; if (sel.length) expand(sel, 1); }}>Expand selected</Button>
        <Button onClick={() => { const sel = cy.current?.$("node:selected").map((n) => n.id()) ?? []; dispatch({ type: "REMOVE_NODES", ids: sel }); }}>Remove</Button>
        <span className="mx-1 h-4 w-px bg-ink-700" />
        <Button disabled={state.multi.length !== 2 || busy} onClick={() => findPath(false)} title="Shift-click two nodes">Shortest path</Button>
        <Button disabled={state.multi.length !== 2 || busy} onClick={() => findPath(true)} title="Only ownership / usage / money-flow / control edges">Constrained path</Button>
        <span className="mx-1 h-4 w-px bg-ink-700" />
        <select className="h-6 rounded-sm border border-ink-600 bg-ink-850 px-1 text-2xs" defaultValue="" onChange={(e) => { if (e.target.value) runAnalytics(e.target.value); e.target.value = ""; }} aria-label="Graph analytics">
          <option value="">Analytics…</option>
          <option value="degree_centrality">Degree centrality</option>
          <option value="betweenness_centrality">Betweenness</option>
          <option value="pagerank">PageRank</option>
        </select>
        {state.analytics && <Button variant="ghost" onClick={() => { dispatch({ type: "SET_ANALYTICS", scores: null }); setAnalyticNote(null); }}>Clear overlay</Button>}
        {state.highlightPath && <Button variant="ghost" onClick={() => dispatch({ type: "HIGHLIGHT_PATH", edgeIds: null })}>Clear path</Button>}
        <span className="ml-auto text-2xs text-ink-400">{nodes.length} nodes · {edges.length} edges {state.multi.length > 0 && `· ${state.multi.length} marked`}</span>
      </div>
      <div ref={ref} className="flex-1 bg-ink-950" data-testid="graph-canvas" />
      {nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 top-8 flex items-center justify-center text-xs text-ink-500">
          Search for an entity to start (Ctrl+K). Double-click a node to expand; shift-click two nodes to find paths.
        </div>
      )}
      {analyticNote && (
        <div className="absolute bottom-2 left-2 max-w-md rounded-sm border border-signal/40 bg-ink-900/95 p-2 text-2xs text-ink-200">
          <SignalTag /> <span className="ml-1">{analyticNote}</span>
          <div className="mt-1 text-ink-400">Node size reflects a mathematical property of the recorded graph window. It is not evidence of importance or wrongdoing.</div>
        </div>
      )}
      <div className="absolute bottom-2 right-2 flex max-w-xs flex-wrap gap-2 rounded-sm bg-ink-900/90 p-1 text-2xs text-ink-300">
        {Object.entries(typeCounts).map(([t, n]) => (
          <span key={t} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLORS[t] }} />{t} {n}</span>
        ))}
      </div>
    </div>
  );
}
