import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { TYPE_COLORS } from "../graph/elements";
import { useActions } from "../state/actions";
import { can, useStore } from "../state/context";
import { initialFilters } from "../state/store";
import { Button, cx, Empty, fmtTime, SignalTag, Tabs, TypeDot } from "./ui";

type Tab = "entities" | "filters" | "alerts" | "review";

export function LeftPanel() {
  const { state } = useStore();
  const [tab, setTab] = useState<Tab>("entities");
  const open = state.alerts.filter((a) => a.status === "OPEN").length;
  return (
    <div className="flex h-full flex-col bg-ink-900">
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "entities", label: "Entities" },
          { id: "filters", label: "Filters" },
          { id: "alerts", label: <span>Alerts {open > 0 && <span className="ml-1 rounded-sm bg-signal/20 px-1 text-signal">{open}</span>}</span> },
          { id: "review", label: "ER" },
        ]}
      />
      <div className="flex-1 overflow-auto">
        {tab === "entities" && <EntityList />}
        {tab === "filters" && <FilterPanel />}
        {tab === "alerts" && <AlertList />}
        {tab === "review" && <ResolutionReview />}
      </div>
    </div>
  );
}

function EntityList() {
  const { state, dispatch } = useStore();
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const g: Record<string, typeof state.nodes[string][]> = {};
    for (const n of Object.values(state.nodes)) {
      if (q && !n.label.toLowerCase().includes(q.toLowerCase())) continue;
      (g[n.type] ??= []).push(n);
    }
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [state.nodes, q]);
  const hidden = new Set(state.filters.hiddenEntityTypes);
  if (!Object.keys(state.nodes).length) return <Empty>No entities in the workspace yet. Use the search bar (Ctrl+K).</Empty>;
  return (
    <div>
      <div className="flex gap-1 p-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter workspace…" className="h-6 flex-1 rounded-sm border border-ink-600 bg-ink-950 px-1 text-xs" />
        <Button variant="ghost" onClick={() => dispatch({ type: "CLEAR" })}>Clear</Button>
      </div>
      {groups.map(([type, items]) => (
        <div key={type}>
          <div className="flex items-center gap-2 bg-ink-850 px-2 py-1 text-2xs uppercase tracking-wider text-ink-400">
            <input
              type="checkbox"
              checked={!hidden.has(type)}
              aria-label={`show ${type}`}
              onChange={() =>
                dispatch({ type: "SET_FILTERS", filters: { hiddenEntityTypes: hidden.has(type) ? state.filters.hiddenEntityTypes.filter((t) => t !== type) : [...state.filters.hiddenEntityTypes, type] } })
              }
            />
            <TypeDot color={TYPE_COLORS[type] ?? "#999"} /> {type} <span className="ml-auto">{items.length}</span>
          </div>
          {items.slice(0, 200).map((n) => (
            <div
              key={n.id}
              onClick={(e) => (e.shiftKey ? dispatch({ type: "TOGGLE_MULTI", id: n.id }) : dispatch({ type: "SELECT", selection: { kind: "entity", id: n.id } }))}
              className={cx(
                "flex cursor-pointer items-center gap-2 px-3 py-[2px] text-xs hover:bg-ink-800",
                state.selection?.kind === "entity" && state.selection.id === n.id && "bg-ink-800",
                state.multi.includes(n.id) && "text-hypo",
              )}
            >
              <span className="truncate">{n.label}</span>
              {n.hop !== undefined && <span className="ml-auto font-mono text-2xs text-ink-500">h{n.hop}</span>}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function FilterPanel() {
  const { state, dispatch, ontology } = useStore();
  const f = state.filters;
  const presentTypes = useMemo(() => [...new Set(Object.values(state.edges).map((e) => e.relationship_type))].sort(), [state.edges]);
  const allRel: string[] = Object.keys(ontology?.relationship_types ?? {}).sort();
  const selected = new Set(f.relationshipTypes ?? allRel);
  const toggle = (t: string) => {
    const next = new Set(selected);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    dispatch({ type: "SET_FILTERS", filters: { relationshipTypes: next.size === allRel.length ? null : [...next] } });
  };
  const statuses = ["DERIVED", "VERIFIED", "SYSTEM_INFERENCE", "ANALYST_ASSERTION"];
  return (
    <div className="space-y-3 p-2 text-xs">
      <div>
        <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Time window (graph, map, timeline)</div>
        <input type="datetime-local" className="mb-1 h-6 w-full rounded-sm border border-ink-600 bg-ink-950 px-1" aria-label="From"
          value={f.timeFrom?.slice(0, 16) ?? ""} onChange={(e) => dispatch({ type: "SET_FILTERS", filters: { timeFrom: e.target.value ? new Date(e.target.value + "Z").toISOString() : null } })} />
        <input type="datetime-local" className="h-6 w-full rounded-sm border border-ink-600 bg-ink-950 px-1" aria-label="To"
          value={f.timeTo?.slice(0, 16) ?? ""} onChange={(e) => dispatch({ type: "SET_FILTERS", filters: { timeTo: e.target.value ? new Date(e.target.value + "Z").toISOString() : null } })} />
      </div>
      <div>
        <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Minimum confidence: {f.minConfidence.toFixed(2)}</div>
        <input type="range" min={0} max={1} step={0.05} value={f.minConfidence} className="w-full" aria-label="Minimum confidence"
          onChange={(e) => dispatch({ type: "SET_FILTERS", filters: { minConfidence: Number(e.target.value) } })} />
      </div>
      <div>
        <div className="mb-1 text-2xs uppercase tracking-wider text-ink-400">Epistemic status</div>
        {statuses.map((s) => (
          <label key={s} className="mr-2 inline-flex items-center gap-1">
            <input type="checkbox" checked={!f.epistemic || f.epistemic.includes(s)}
              onChange={() => {
                const cur = new Set(f.epistemic ?? statuses);
                if (cur.has(s)) cur.delete(s);
                else cur.add(s);
                dispatch({ type: "SET_FILTERS", filters: { epistemic: cur.size === statuses.length ? null : [...cur] } });
              }} />
            <span className="text-2xs">{s}</span>
          </label>
        ))}
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between text-2xs uppercase tracking-wider text-ink-400">
          Relationship types
          <button className="normal-case text-accent" onClick={() => dispatch({ type: "SET_FILTERS", filters: { relationshipTypes: null } })}>all</button>
        </div>
        {allRel.map((t) => (
          <label key={t} className={cx("flex items-center gap-1 py-[1px]", !presentTypes.includes(t) && "text-ink-500")}>
            <input type="checkbox" checked={selected.has(t)} onChange={() => toggle(t)} /> <span className="font-mono text-2xs">{t}</span>
          </label>
        ))}
      </div>
      <Button onClick={() => dispatch({ type: "SET_FILTERS", filters: initialFilters })}>Reset filters</Button>
      <div className="text-2xs text-ink-500">Filters apply to the workspace view and to new expansions (server-side).</div>
    </div>
  );
}

function AlertList() {
  const { state, dispatch, me } = useStore();
  const { fail } = useActions();
  const [status, setStatus] = useState("OPEN");
  useEffect(() => {
    api.alerts().then((r) => dispatch({ type: "SET_ALERTS", alerts: r.items })).catch(fail);
  }, [dispatch, fail]);
  const items = state.alerts.filter((a) => !status || a.status === status);
  const update = async (id: string, s: string) => {
    try {
      const a = await api.patchAlert(id, s, "updated from workbench");
      dispatch({ type: "PUSH_ALERT", alert: a });
    } catch (e) {
      fail(e);
    }
  };
  return (
    <div>
      <div className="flex gap-1 p-2">
        {["OPEN", "ACKNOWLEDGED", "ESCALATED", "DISMISSED", ""].map((s) => (
          <Button key={s || "all"} variant={status === s ? "primary" : "default"} onClick={() => setStatus(s)}>{s || "ALL"}</Button>
        ))}
      </div>
      {items.map((a) => (
        <div key={a.id} className="border-b border-ink-800 p-2 text-xs">
          <div className="flex items-center gap-1">
            <SignalTag />
            <span className="text-2xs text-ink-400">{a.severity}</span>
            <span className="ml-auto font-mono text-2xs text-ink-500">{fmtTime(a.timestamp)}</span>
          </div>
          <div className="mt-1 cursor-pointer text-ink-200 hover:text-white" onClick={() => a.signal_id && dispatch({ type: "SELECT", selection: { kind: "signal", id: a.signal_id } })}>
            {a.summary}
          </div>
          {can(me, "alerts:manage") && (
            <div className="mt-1 flex gap-1">
              <Button variant="ghost" onClick={() => update(a.id, "ACKNOWLEDGED")}>Ack</Button>
              <Button variant="ghost" onClick={() => update(a.id, "ESCALATED")}>Escalate</Button>
              <Button variant="ghost" onClick={() => update(a.id, "DISMISSED")}>Dismiss</Button>
            </div>
          )}
        </div>
      ))}
      {!items.length && <Empty>No alerts.</Empty>}
    </div>
  );
}

function ResolutionReview() {
  const { me, dispatch } = useStore();
  const { addEntity, fail } = useActions();
  const [items, setItems] = useState<any[]>([]);
  const load = () => api.resolutionCandidates("POSSIBLE_MATCH").then((r) => setItems(r.items)).catch(fail);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const review = async (id: string, d: "CONFIRM" | "REJECT") => {
    try {
      await api.reviewCandidate(id, d, "reviewed in workbench");
      dispatch({ type: "TOAST", level: "info", text: d === "CONFIRM" ? "Entities merged (reversible; audited)" : "Marked as distinct" });
      load();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <div>
      <div className="p-2 text-2xs text-ink-400">POSSIBLE_MATCH candidates are never merged automatically. Review the evidence before deciding.</div>
      {items.map((c) => (
        <div key={c.id} className="border-b border-ink-800 p-2 text-xs">
          <div className="flex items-center justify-between"><span className="text-signal">{c.decision}</span><span className="font-mono">{c.score.toFixed(3)}</span></div>
          <div className="cursor-pointer text-ink-200" onClick={() => c.a && addEntity(c.a.id)}>A: {c.a?.label}</div>
          <div className="cursor-pointer text-ink-200" onClick={() => c.b && addEntity(c.b.id)}>B: {c.b?.label}</div>
          <ul className="mt-1 text-2xs text-ink-400">{c.evidence.map((e: any, i: number) => <li key={i}>{e.detail}</li>)}</ul>
          <div className="mt-1 text-2xs text-ink-500">{c.review_status}</div>
          {can(me, "er:review") && c.review_status === "UNREVIEWED" && (
            <div className="mt-1 flex gap-1">
              <Button onClick={() => review(c.id, "CONFIRM")}>Confirm & merge</Button>
              <Button onClick={() => review(c.id, "REJECT")}>Distinct</Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
