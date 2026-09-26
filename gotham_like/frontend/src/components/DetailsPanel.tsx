import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EntityDetail, Provenance, Signal } from "../api/types";
import { TYPE_COLORS } from "../graph/elements";
import { useActions } from "../state/actions";
import { can, useStore } from "../state/context";
import { Button, Empty, fmtPct, fmtTime, KV, PanelHeader, Section, SignalTag, StatusBadge, TypeDot } from "./ui";

export function DetailsPanel() {
  const { state } = useStore();
  const sel = state.selection;
  return (
    <div className="flex h-full flex-col bg-ink-900">
      <PanelHeader title={sel ? `${sel.kind} details` : "Evidence / details"} />
      <div className="flex-1 overflow-auto">
        {!sel && <Empty>Select an entity, relationship, event or signal to inspect its evidence and provenance.</Empty>}
        {sel?.kind === "entity" && <EntityCard id={sel.id} />}
        {sel?.kind === "edge" && <EdgeProvenance id={sel.id} />}
        {sel?.kind === "event" && <ProvenanceView id={sel.id} />}
        {sel?.kind === "signal" && <SignalCard id={sel.id} />}
      </div>
    </div>
  );
}

export function EntityCard({ id }: { id: string }) {
  const { state, dispatch, me } = useStore();
  const { expand, pin, fail } = useActions();
  const [e, setE] = useState<EntityDetail | null>(null);
  const [hypo, setHypo] = useState("");

  useEffect(() => {
    setE(null);
    api.entity(id).then(setE).catch(fail);
  }, [id, fail]);

  if (!e) return <Empty>Loading…</Empty>;
  const props = Object.entries(e.properties).filter(([k]) => !k.startsWith("_"));
  const alternates = (e.properties._alternates ?? {}) as Record<string, unknown[]>;

  const createHypothesis = async () => {
    try {
      await api.createAssertion({ statement: hypo, subject_ids: [e.id], investigation_id: state.investigationId, rationale: "Created from entity card" });
      setHypo("");
      dispatch({ type: "TOAST", level: "info", text: "Hypothesis recorded (ANALYST ASSERTION — HYPOTHESIS)" });
      api.entity(id).then(setE);
    } catch (err) {
      fail(err);
    }
  };

  return (
    <div>
      <div className="border-b border-ink-800 p-2">
        <div className="flex items-center gap-2">
          <TypeDot color={TYPE_COLORS[e.type] ?? "#999"} />
          <span className="text-2xs uppercase tracking-wider text-ink-400">{e.type}</span>
          <StatusBadge status={e.epistemic_status} />
          <span className="ml-auto font-mono text-2xs text-ink-500" title="Confidence in the derived entity (lowered by entity-resolution merges)">conf {fmtPct(e.confidence)}</span>
        </div>
        <div className="mt-1 text-sm font-semibold text-ink-100" data-testid="entity-label">{e.label}</div>
        <div className="font-mono text-2xs text-ink-500">{e.id}</div>
        {e.redirected_from && <div className="mt-1 text-2xs text-signal">Redirected from merged entity {e.redirected_from}</div>}
        <div className="mt-2 flex flex-wrap gap-1">
          <Button onClick={() => expand([e.id], 1)}>Expand 1-hop</Button>
          <Button onClick={() => expand([e.id], 2)}>2-hop</Button>
          <Button onClick={() => dispatch({ type: "SET_MODE", mode: "entity" })}>Profile</Button>
          <Button onClick={() => { dispatch({ type: "SET_MODE", mode: "timeline" }); }}>Timeline</Button>
          <Button onClick={() => dispatch({ type: "SET_MODE", mode: "map" })}>Map</Button>
          <Button onClick={() => pin("entity", e.id, `${e.type}: ${e.label}`)} disabled={!can(me, "investigation:write")}>Pin</Button>
        </div>
      </div>
      <Section title={`Properties ${e.masked_fields.length ? `(${e.masked_fields.length} masked for ${me.role})` : ""}`}>
        <KV rows={props.map(([k, v]) => [k, <span className={e.masked_fields.includes(k) ? "text-ink-500" : ""}>{String(v)}</span>])} />
        {Object.keys(alternates).length > 0 && (
          <div className="mt-1 text-2xs text-ink-400">
            Alternate values from merged records: {Object.entries(alternates).map(([k, v]) => `${k}: ${(v as unknown[]).join(" | ")}`).join("; ")}
          </div>
        )}
      </Section>
      <Section title="Relationships">
        <div className="flex flex-wrap gap-1">
          {Object.entries(e.degree).map(([t, n]) => (
            <span key={t} className="rounded-sm bg-ink-800 px-1 font-mono text-2xs">{t} {n}</span>
          ))}
        </div>
      </Section>
      {e.signals.length > 0 && (
        <Section title={<span className="flex items-center gap-1"><SignalTag /> {e.signals.length}</span>}>
          {e.signals.map((s) => (
            <div key={s.id} className="mb-1 cursor-pointer rounded-sm border border-ink-700 p-1 hover:border-signal/60" onClick={() => dispatch({ type: "SELECT", selection: { kind: "signal", id: s.id } })}>
              <div className="text-2xs font-semibold text-signal">{s.rule_id}</div>
              <div className="text-xs text-ink-200">{s.what}</div>
            </div>
          ))}
          <div className="text-2xs text-ink-500">Signals are prompts for review, not conclusions.</div>
        </Section>
      )}
      <Section title="Provenance">
        <KV rows={[
          ["source records", e.source_ids.length],
          ["classification", e.classification],
          ["transformation", String(e.provenance.transformation ?? "")],
          ["version", String(e.provenance.transformation_version ?? "")],
          ["updated", fmtTime(e.updated_at)],
        ]} />
        {(e.provenance.resolution ?? []).map((r) => (
          <div key={r.merged} className="mt-1 rounded-sm border border-signal/30 p-1 text-2xs">
            <div className="flex items-center gap-1"><StatusBadge status="SYSTEM_INFERENCE" /> merged <span className="font-mono">{r.merged}</span> · score {r.score}</div>
            <div className="text-ink-400">{r.reasons.join(" · ")}</div>
          </div>
        ))}
        <Button className="mt-1" onClick={() => dispatch({ type: "SELECT", selection: { kind: "event", id: e.id } })}>Full lineage</Button>
      </Section>
      {e.resolution_candidates.filter((c) => !c.merged).length > 0 && (
        <Section title="Possible duplicates (unmerged)">
          {e.resolution_candidates.filter((c) => !c.merged).map((c) => (
            <div key={c.id} className="text-2xs text-ink-300">{c.decision} {c.score.toFixed(2)} · <span className="font-mono">{c.other}</span> · {c.review_status}</div>
          ))}
        </Section>
      )}
      <Section title="Analyst assertions">
        {e.assertions.map((a) => (
          <div key={a.id} className="mb-1 text-xs"><StatusBadge status="ANALYST_ASSERTION" /> <span className="text-hypo">{a.status}</span> — {a.statement}</div>
        ))}
        {can(me, "assertion:write") && (
          <div className="mt-1 flex gap-1">
            <input value={hypo} onChange={(ev) => setHypo(ev.target.value)} placeholder="Record a hypothesis…" className="h-6 flex-1 rounded-sm border border-ink-600 bg-ink-950 px-1 text-xs" />
            <Button disabled={hypo.length < 5} onClick={createHypothesis}>Add</Button>
          </div>
        )}
      </Section>
    </div>
  );
}

export function EdgeProvenance({ id }: { id: string }) {
  return <ProvenanceView id={id} edge />;
}

export function ProvenanceView({ id, edge = false }: { id: string; edge?: boolean }) {
  const { dispatch, me } = useStore();
  const { pin, fail } = useActions();
  const [p, setP] = useState<Provenance | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => {
    setP(null);
    api.provenance(id).then(setP).catch(fail);
  }, [id, fail]);
  if (!p) return <Empty>Loading provenance…</Empty>;
  const o = p.object as Record<string, any>;
  const review = async (action: string) => {
    try {
      await api.reviewRelationship(id, action, note);
      setNote("");
      api.provenance(id).then(setP);
      dispatch({ type: "TOAST", level: "info", text: `Relationship ${action} recorded (audited)` });
    } catch (e) {
      fail(e);
    }
  };
  return (
    <div>
      <Section title={edge ? "Why does this relationship exist?" : `Why does this ${p.kind} exist?`}>
        <div className="flex items-center gap-2 text-xs">
          <StatusBadge status={p.epistemic_status} />
          {edge && <span className="font-semibold">{o.relationship_type}</span>}
          {p.kind === "event" && <span className="font-semibold">{o.event_type}</span>}
        </div>
        <p className="mt-1 text-xs text-ink-200">{p.why}</p>
        {edge && (
          <KV rows={[
            ["source → target", `${o.source} → ${o.target}`],
            ["timestamp", fmtTime(o.timestamp)],
            ["confidence", fmtPct(o.confidence)],
            ["transformation", `${o.provenance?.transformation} (${o.provenance?.transformation_version})`],
            ["ingestion run", o.provenance?.ingestion_run],
          ]} />
        )}
        {p.kind === "event" && <KV rows={[["time", fmtTime(o.timestamp)], ["source", o.source], ["entities", (o.entity_ids ?? []).length]]} />}
        <div className="mt-1 flex gap-1">
          {edge && <Button onClick={() => pin("relationship", id, `${o.relationship_type} ${o.source} → ${o.target}`)}>Pin relationship</Button>}
          {p.kind === "event" && <Button onClick={() => pin("event", id, `${o.event_type} @ ${fmtTime(o.timestamp)}`)}>Pin event</Button>}
        </div>
      </Section>
      <Section title={`Source records (${p.source_records_total})`}>
        {p.source_records.slice(0, 10).map((r) => (
          <div key={r.id} className="mb-1 rounded-sm border border-ink-700 p-1">
            <div className="flex items-center gap-1 text-2xs"><StatusBadge status="RAW" /> <span className="font-semibold">{r.source.name}</span></div>
            <KV rows={[["record", r.source_record_id], ["ingested", fmtTime(r.ingestion_timestamp)], ["transformation", r.transformation_version], ["hash", r.content_hash.slice(0, 16) + "…"]]} />
            <details className="mt-1 text-2xs">
              <summary className="cursor-pointer text-ink-400">payload</summary>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-2xs text-ink-300">{typeof r.payload === "string" ? r.payload : JSON.stringify(r.payload, null, 1)}</pre>
            </details>
            <Button variant="ghost" onClick={() => pin("citation", r.id, `Source record ${r.source_record_id}`, { source_record_id: r.id })}>Cite</Button>
          </div>
        ))}
      </Section>
      <Section title="Lineage (upstream)">
        {p.lineage_upstream.edges.slice(0, 20).map((l, i) => (
          <div key={i} className="font-mono text-2xs text-ink-300">{l.from} ⟶ {l.to} <span className="text-ink-500">[{l.transformation} {l.transformation_version}]</span></div>
        ))}
        {p.lineage_upstream.edges.length === 0 && <div className="text-2xs text-ink-500">This is an original record.</div>}
      </Section>
      {(p.analyst_modifications ?? []).length > 0 && (
        <Section title="Analyst modifications">
          {p.analyst_modifications!.map((m: any, i) => (
            <div key={i} className="text-2xs text-ink-300">{fmtTime(m.at)} · {m.by} · <b>{m.action}</b> — {m.note} (was {m.previous_status})</div>
          ))}
        </Section>
      )}
      {edge && can(me, "relationship:verify") && (
        <Section title="Review (audited)">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Justification (required)" className="h-6 w-full rounded-sm border border-ink-600 bg-ink-950 px-1 text-xs" />
          <div className="mt-1 flex gap-1">
            <Button disabled={note.length < 3} onClick={() => review("verify")}>Mark verified</Button>
            <Button disabled={note.length < 3} onClick={() => review("dispute")}>Dispute</Button>
            <Button disabled={note.length < 3} onClick={() => review("annotate")}>Annotate</Button>
          </div>
        </Section>
      )}
    </div>
  );
}

export function SignalCard({ id }: { id: string }) {
  const { dispatch } = useStore();
  const { addEntity, pin, fail } = useActions();
  const [s, setS] = useState<Signal | null>(null);
  useEffect(() => {
    api.signal(id).then(setS).catch(fail);
  }, [id, fail]);
  if (!s) return <Empty>Loading…</Empty>;
  const x = s.explanation;
  return (
    <div data-testid="signal-card">
      <Section title={<span className="flex items-center gap-1"><SignalTag /> {s.rule_id} v{s.rule_version}</span>}>
        <div className="text-2xs text-ink-400">Analytical signal detected. This is not a finding about any person or organisation.</div>
      </Section>
      <Section title="What happened?"><p className="text-xs">{x.what_happened}</p></Section>
      <Section title="Why did the system show this?"><p className="text-xs">{x.why_shown}</p></Section>
      <Section title="Which data supports it?">
        <div className="text-xs">{x.supporting_data.evidence_items} evidence item(s) · {x.supporting_data.source_records_total} source record(s)</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {s.entity_ids.slice(0, 12).map((eid) => (
            <button key={eid} className="rounded-sm bg-ink-800 px-1 font-mono text-2xs hover:bg-ink-700" onClick={() => addEntity(eid)}>{eid}</button>
          ))}
        </div>
        <Button className="mt-1" onClick={async () => { for (const eid of s.entity_ids.slice(0, 30)) await addEntity(eid, false); dispatch({ type: "SET_MODE", mode: "graph" }); }}>
          Add all to graph
        </Button>
      </Section>
      <Section title="When was the data collected?">
        <KV rows={[["ingested", `${fmtTime(x.data_collected.ingested_from)} → ${fmtTime(x.data_collected.ingested_to)}`], ["time window", `${fmtTime(x.time_window.start)} → ${fmtTime(x.time_window.end)}`]]} />
      </Section>
      <Section title="What assumptions were used?"><ul className="list-disc pl-4 text-xs">{x.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Section>
      <Section title="What is uncertain?"><ul className="list-disc pl-4 text-xs">{x.uncertain.map((a) => <li key={a}>{a}</li>)}</ul></Section>
      <Section title="Alternative explanations"><ul className="list-disc pl-4 text-xs text-ink-200">{x.alternative_explanations.map((a) => <li key={a}>{a}</li>)}</ul></Section>
      <Section title="Score"><div className="text-xs">{s.score} — <span className="text-ink-400">{x.score_meaning}</span></div></Section>
      <div className="p-2"><Button onClick={() => pin("signal", s.id, `Signal ${s.rule_id}`)}>Pin signal to investigation</Button></div>
    </div>
  );
}
