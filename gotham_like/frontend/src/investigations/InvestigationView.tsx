import { useCallback, useEffect, useState } from "react";
import { api, download } from "../api/client";
import type { InvestigationFull, Investigation } from "../api/types";
import { Button, Empty, fmtTime, PanelHeader, SignalTag, StatusBadge } from "../components/ui";
import { useActions } from "../state/actions";
import { can, useStore } from "../state/context";
import { subscribeInvestigation } from "../state/realtime";

export function InvestigationView() {
  const { state, dispatch, me } = useStore();
  const { fail } = useActions();
  const [list, setList] = useState<Investigation[]>([]);
  const [inv, setInv] = useState<InvestigationFull | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [note, setNote] = useState("");
  const [citation, setCitation] = useState("");
  const [hypo, setHypo] = useState("");
  const [presence, setPresence] = useState<string[]>([]);

  const loadList = useCallback(() => api.investigations().then(setList).catch(fail), [fail]);
  const load = useCallback((id: string) => api.investigation(id).then(setInv).catch(fail), [fail]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    if (!state.investigationId) { setInv(null); return; }
    load(state.investigationId);
    return subscribeInvestigation(state.investigationId, (msg) => {
      if (msg.event === "presence") setPresence((p) => [...new Set([...p, String(msg.payload.user)])]);
      else {
        load(state.investigationId!);
        if (msg.payload?.by && msg.payload.by !== me.username) dispatch({ type: "TOAST", level: "info", text: `${msg.payload.by}: ${msg.event}` });
      }
    });
  }, [state.investigationId, load, dispatch, me.username]);

  const create = async () => {
    try {
      const i = await api.createInvestigation(name, desc, { question: desc, created_from: "workbench" });
      setName(""); setDesc("");
      await loadList();
      dispatch({ type: "SET_INVESTIGATION", id: i.id });
    } catch (e) { fail(e); }
  };

  const addItem = async (body: Record<string, unknown>) => {
    if (!inv) return;
    try { await api.addItem(inv.id, body); load(inv.id); } catch (e) { fail(e); }
  };

  const pinWorkspace = async () => {
    if (!inv) return;
    const pinned = new Set(inv.items.filter((i) => i.kind === "entity").map((i) => i.ref_id));
    for (const n of Object.values(state.nodes)) {
      if (!pinned.has(n.id)) await api.addItem(inv.id, { kind: "entity", ref_id: n.id, title: `${n.type}: ${n.label}` }).catch(fail);
    }
    load(inv.id);
  };

  const openInGraph = async () => {
    if (!inv) return;
    const ids = inv.items.filter((i) => i.kind === "entity" && i.ref_id).map((i) => i.ref_id!) as string[];
    if (!ids.length) return;
    try {
      const g = await api.subgraph(ids.slice(0, 200), 0, {}, 500);
      dispatch({ type: "ADD_GRAPH", nodes: g.nodes, edges: [] });
      const rels = inv.items.filter((i) => i.kind === "relationship" && i.ref_id);
      const edges = [];
      for (const r of rels.slice(0, 100)) {
        const p = await api.provenance(r.ref_id!);
        const o = p.object as any;
        edges.push({ ...o, source: o.source, target: o.target });
      }
      const exp = await api.subgraph(ids.slice(0, 200), 1, {}, 800);
      dispatch({ type: "ADD_GRAPH", nodes: [], edges: [...edges, ...exp.edges.filter((e) => ids.includes(e.source) && ids.includes(e.target))] });
      dispatch({ type: "SET_MODE", mode: "graph" });
    } catch (e) { fail(e); }
  };

  const report = async (format: "pdf" | "markdown" | "json") => {
    if (!inv) return;
    try { download(await api.report(inv.id, format), `${inv.id}-report.${format === "markdown" ? "md" : format}`); } catch (e) { fail(e); }
  };
  const exportData = async (format: string, what = "entities") => {
    if (!inv) return;
    try { download(await api.exportData({ format, investigation_id: inv.id, what }), `${inv.id}-${what}.${format}`); } catch (e) { fail(e); }
  };

  if (!inv) {
    return (
      <div className="flex h-full flex-col">
        <PanelHeader title="Investigations" />
        <div className="grid flex-1 grid-cols-2 gap-4 overflow-auto p-3">
          <div>
            <div className="mb-2 text-2xs uppercase tracking-wider text-ink-400">Open</div>
            {list.map((i) => (
              <div key={i.id} className="mb-1 cursor-pointer rounded-sm border border-ink-700 p-2 hover:border-accent" onClick={() => dispatch({ type: "SET_INVESTIGATION", id: i.id })}>
                <div className="text-xs font-semibold">{i.name}</div>
                <div className="text-2xs text-ink-400">{i.status} · updated {fmtTime(i.updated_at)} · v{i.version}</div>
              </div>
            ))}
            {!list.length && <Empty>No investigations yet.</Empty>}
          </div>
          {can(me, "investigation:write") && (
            <div>
              <div className="mb-2 text-2xs uppercase tracking-wider text-ink-400">New investigation</div>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="mb-1 h-7 w-full rounded-sm border border-ink-600 bg-ink-950 px-2 text-xs" />
              <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Question / scope" rows={4} className="mb-1 w-full rounded-sm border border-ink-600 bg-ink-950 p-2 text-xs" />
              <Button variant="primary" disabled={!name} onClick={create}>Create</Button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const by = (k: string) => inv.items.filter((i) => i.kind === k);
  const evidence = inv.items.filter((i) => ["note", "citation", "document", "source_record", "event", "map", "timeline", "chart", "saved_query"].includes(i.kind));
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-ink-800 bg-ink-900 p-2">
        <button className="text-ink-400 hover:text-white" onClick={() => dispatch({ type: "SET_INVESTIGATION", id: null })}>←</button>
        <div>
          <div className="text-sm font-semibold" data-testid="investigation-name">{inv.name}</div>
          <div className="text-2xs text-ink-400">{inv.description}</div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-1">
          {presence.length > 0 && <span className="text-2xs text-ink-400">viewing: {presence.join(", ")}</span>}
          <span className="text-2xs text-ink-500">v{inv.version} · {inv.status}</span>
          {inv.can_write && <Button onClick={pinWorkspace}>Pin workspace entities</Button>}
          <Button onClick={openInGraph}>Open in graph</Button>
          <Button onClick={() => report("pdf")}>Report PDF</Button>
          <Button onClick={() => report("markdown")}>Report MD</Button>
          <select className="h-6 rounded-sm border border-ink-600 bg-ink-850 px-1 text-2xs" defaultValue="" aria-label="Export"
            onChange={(e) => { const [f, w] = e.target.value.split("/"); if (f) exportData(f, w); e.target.value = ""; }}>
            <option value="">Export…</option>
            <option value="csv/entities">CSV entities</option><option value="csv/relationships">CSV relationships</option><option value="csv/events">CSV events</option>
            <option value="json/entities">JSON</option><option value="graphml/entities">GraphML</option><option value="geojson/entities">GeoJSON</option>
          </select>
          {inv.can_write && inv.status !== "CLOSED" && (
            <Button variant="ghost" onClick={() => api.patchInvestigation(inv.id, { status: "CLOSED", expected_version: inv.version }).then(() => load(inv.id)).catch(fail)}>Close</Button>
          )}
        </div>
      </div>
      <div className="grid flex-1 grid-cols-4 gap-px overflow-hidden bg-ink-800">
        <Column title={`Entities (${by("entity").length})`}>
          {by("entity").map((i) => (
            <Item key={i.id} onClick={() => i.ref_id && dispatch({ type: "SELECT", selection: { kind: "entity", id: i.ref_id } })} onRemove={inv.can_write ? () => api.removeItem(inv.id, i.id).then(() => load(inv.id)) : undefined}>
              <StatusBadge status={i.epistemic_status} /> {i.title}
            </Item>
          ))}
        </Column>
        <Column title={`Relationships & signals (${by("relationship").length + by("signal").length})`}>
          {by("relationship").map((i) => (
            <Item key={i.id} onClick={() => i.ref_id && dispatch({ type: "SELECT", selection: { kind: "edge", id: i.ref_id } })} onRemove={inv.can_write ? () => api.removeItem(inv.id, i.id).then(() => load(inv.id)) : undefined}>
              <StatusBadge status={i.epistemic_status} /> {i.title}
              <div className="text-2xs text-ink-500">{((i.provenance.source_records as string[]) ?? []).length} source record(s)</div>
            </Item>
          ))}
          {by("signal").map((i) => (
            <Item key={i.id} onClick={() => i.ref_id && dispatch({ type: "SELECT", selection: { kind: "signal", id: i.ref_id } })}>
              <SignalTag /> {i.title}
            </Item>
          ))}
        </Column>
        <Column title={`Evidence (${evidence.length})`}>
          {evidence.map((i) => (
            <Item key={i.id} onClick={() => i.kind === "event" && i.ref_id ? dispatch({ type: "SELECT", selection: { kind: "event", id: i.ref_id } }) : undefined}
              onRemove={inv.can_write ? () => api.removeItem(inv.id, i.id).then(() => load(inv.id)) : undefined}>
              <span className="text-2xs uppercase text-ink-400">{i.kind}</span> <StatusBadge status={i.epistemic_status} />
              <div>{i.title}</div>
              {typeof i.content.text === "string" && <div className="text-2xs text-ink-300">{i.content.text}</div>}
              {typeof i.content.reference === "string" && <div className="text-2xs text-ink-300">{i.content.reference}</div>}
              <div className="text-2xs text-ink-500">by {String(i.provenance.pinned_by ?? i.created_by)} · {fmtTime(i.created_at)}</div>
            </Item>
          ))}
          {inv.can_write && (
            <div className="mt-2 space-y-1">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add note…" rows={2} className="w-full rounded-sm border border-ink-600 bg-ink-950 p-1 text-xs" />
              <Button disabled={!note} onClick={() => { addItem({ kind: "note", title: note.slice(0, 80), content: { text: note } }); setNote(""); }}>Add note</Button>
              <input value={citation} onChange={(e) => setCitation(e.target.value)} placeholder="Citation / reference…" className="h-6 w-full rounded-sm border border-ink-600 bg-ink-950 px-1 text-xs" />
              <Button disabled={!citation} onClick={() => { addItem({ kind: "citation", title: citation.slice(0, 80), content: { reference: citation } }); setCitation(""); }}>Add citation</Button>
              <label className="block text-2xs text-ink-400">Attach document
                <input type="file" className="block text-2xs" onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  const fd = new FormData(); fd.append("file", f); fd.append("title", f.name);
                  try { await fetch(`/api/investigations/${inv.id}/documents`, { method: "POST", body: fd, headers: { Authorization: `Bearer ${sessionStorage.getItem("tessera.token")}` } }); load(inv.id); } catch (err) { fail(err); }
                }} />
              </label>
            </div>
          )}
        </Column>
        <Column title={`Hypotheses (${inv.assertions.length})`}>
          <div className="mb-2 text-2xs text-ink-500">Analyst assertions are kept separate from source-derived facts.</div>
          {inv.assertions.map((a) => (
            <div key={a.id} className="mb-1 rounded-sm border border-hypo/30 p-1 text-xs">
              <div className="text-2xs font-semibold text-hypo">{a.label}</div>
              <div>{a.statement}</div>
              <div className="text-2xs text-ink-500">{a.subject_ids.length} subject(s) · {a.history.length} change(s)</div>
              {can(me, "assertion:write") && (
                <div className="mt-1 flex gap-1">
                  {["SUPPORTED", "REFUTED", "WITHDRAWN"].map((s) => (
                    <Button key={s} variant="ghost" onClick={() => api.patchAssertion(a.id, { status: s, note: `set to ${s}` }).then(() => load(inv.id)).catch(fail)}>{s.toLowerCase()}</Button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {can(me, "assertion:write") && (
            <div className="mt-2 space-y-1">
              <textarea value={hypo} onChange={(e) => setHypo(e.target.value)} placeholder="Entity A may be associated with Entity B…" rows={3} className="w-full rounded-sm border border-ink-600 bg-ink-950 p-1 text-xs" />
              <Button disabled={hypo.length < 5 || !(state.multi.length || (state.selection?.kind === "entity"))}
                title="Subjects: shift-marked nodes, or the selected entity"
                onClick={() => {
                  const subjects = state.multi.length ? state.multi : state.selection?.kind === "entity" ? [state.selection.id] : [];
                  api.createAssertion({ statement: hypo, subject_ids: subjects, investigation_id: inv.id, rationale: "" }).then(() => { setHypo(""); load(inv.id); }).catch(fail);
                }}>
                Create hypothesis
              </Button>
            </div>
          )}
        </Column>
      </div>
    </div>
  );
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col overflow-hidden bg-ink-900">
      <PanelHeader title={title} />
      <div className="flex-1 overflow-auto p-2">{children}</div>
    </div>
  );
}

function Item({ children, onClick, onRemove }: { children: React.ReactNode; onClick?: () => void; onRemove?: () => void }) {
  return (
    <div className="group mb-1 flex cursor-pointer items-start gap-1 rounded-sm border border-ink-700 p-1 text-xs hover:border-ink-500" onClick={onClick}>
      <div className="flex-1">{children}</div>
      {onRemove && <button className="invisible text-ink-500 hover:text-danger group-hover:visible" onClick={(e) => { e.stopPropagation(); onRemove(); }}>×</button>}
    </div>
  );
}
