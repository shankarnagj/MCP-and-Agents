import { useEffect } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { api } from "../api/client";
import type { Alert } from "../api/types";
import { DetailsPanel } from "../components/DetailsPanel";
import { LeftPanel } from "../components/LeftPanel";
import { EntityProfile, TableView } from "../components/TableView";
import { cx, Tabs } from "../components/ui";
import { GraphView } from "../graph/GraphView";
import { InvestigationView } from "../investigations/InvestigationView";
import { MapView } from "../map/MapView";
import { QueryBuilder } from "../query/QueryBuilder";
import { CommandBar } from "../search/CommandBar";
import { useStore } from "../state/context";
import { connect, on } from "../state/realtime";
import type { Mode } from "../state/store";
import { TimelineView } from "../timeline/TimelineView";

const MODES: { id: Mode; label: string }[] = [
  { id: "graph", label: "Graph" }, { id: "map", label: "Map" }, { id: "timeline", label: "Timeline" }, { id: "table", label: "Table" },
  { id: "entity", label: "Entity" }, { id: "investigation", label: "Investigation" }, { id: "query", label: "Query" },
];

const Handle = ({ dir }: { dir: "h" | "v" }) => (
  <PanelResizeHandle className={cx("bg-ink-800 transition-colors hover:bg-accent-dim", dir === "h" ? "w-[3px]" : "h-[3px]")} />
);

export function Workspace({ onLogout }: { onLogout: () => void }) {
  const { state, dispatch } = useStore();

  useEffect(() => {
    connect();
    const off = on("alerts", (m) => {
      if (m.event === "alert.created" || m.event === "alert.updated") {
        dispatch({ type: "PUSH_ALERT", alert: m.payload as Alert });
        if (m.event === "alert.created") dispatch({ type: "TOAST", level: "signal", text: `Analytical signal detected: ${(m.payload as Alert).summary.slice(0, 120)}` });
      }
    });
    api.alerts().then((r) => dispatch({ type: "SET_ALERTS", alerts: r.items })).catch(() => undefined);
    return () => { off(); };
  }, [dispatch]);

  useEffect(() => {
    const t = state.toasts[0];
    if (!t) return;
    const h = setTimeout(() => dispatch({ type: "DISMISS_TOAST", id: t.id }), t.level === "error" ? 8000 : 5000);
    return () => clearTimeout(h);
  }, [state.toasts, dispatch]);

  const main = () => {
    switch (state.mode) {
      case "graph": return <GraphView />;
      case "map": return <MapView />;
      case "timeline": return <TimelineView />;
      case "table": return <TableView />;
      case "entity": return <EntityProfile />;
      case "investigation": return <InvestigationView />;
      case "query": return <QueryBuilder />;
    }
  };

  return (
    <div className="flex h-full flex-col">
      <CommandBar />
      <PanelGroup direction="vertical" className="flex-1" autoSaveId="tessera-v">
        <Panel defaultSize={74} minSize={30}>
          <PanelGroup direction="horizontal" autoSaveId="tessera-h">
            <Panel defaultSize={17} minSize={10}><LeftPanel /></Panel>
            <Handle dir="h" />
            <Panel defaultSize={58} minSize={30}>
              <div className="flex h-full flex-col">
                <Tabs<Mode>
                  value={state.mode}
                  onChange={(m) => dispatch({ type: "SET_MODE", mode: m })}
                  tabs={MODES}
                  right={
                    <>
                      {state.investigationId && <span className="text-2xs text-hypo">investigation active</span>}
                      <button className="text-2xs text-ink-400 hover:text-white" onClick={onLogout}>Sign out</button>
                    </>
                  }
                />
                <div className="relative flex-1 overflow-hidden">{main()}</div>
              </div>
            </Panel>
            <Handle dir="h" />
            <Panel defaultSize={25} minSize={15}><DetailsPanel /></Panel>
          </PanelGroup>
        </Panel>
        <Handle dir="v" />
        <Panel defaultSize={26} minSize={8}>
          <div className="h-full bg-ink-900">{state.mode !== "timeline" ? <TimelineView compact /> : <TableView />}</div>
        </Panel>
      </PanelGroup>
      <div className="pointer-events-none fixed bottom-3 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-1">
        {state.toasts.map((t) => (
          <div key={t.id} role="status" className={cx("pointer-events-auto rounded-sm border px-3 py-1 text-xs shadow-lg",
            t.level === "error" ? "border-danger/60 bg-ink-900 text-danger" : t.level === "signal" ? "border-signal/60 bg-ink-900 text-signal" : "border-ink-600 bg-ink-900 text-ink-100")}
            onClick={() => dispatch({ type: "DISMISS_TOAST", id: t.id })}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
