import * as echarts from "echarts/core";
import { BarChart, ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { TimelineResponse } from "../api/types";
import { Button, fmtTime } from "../components/ui";
import { useActions } from "../state/actions";
import { useStore } from "../state/context";

echarts.use([BarChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer]);

const PALETTE = ["#4ea1ff", "#e0a341", "#57d3c1", "#e5534b", "#b48cff", "#7fd46a", "#e67fb8", "#f0b35e", "#8b98ad", "#43c59e", "#d6c35a", "#6fb6ff"];

export function TimelineView({ compact = false }: { compact?: boolean }) {
  const { state, dispatch } = useStore();
  const { fail } = useActions();
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [bucket, setBucket] = useState<"hour" | "day" | "week">("day");
  const [types, setTypes] = useState<string[] | null>(null);
  const [zoomWindow, setZoomWindow] = useState<[string, string] | null>(null);
  const ids = useMemo(() => Object.keys(state.nodes), [state.nodes]);

  useEffect(() => {
    api.timeline({ entity_id: ids.slice(0, 200), event_type: types ?? undefined, bucket, limit: compact ? 1000 : 3000,
                   time_from: state.filters.timeFrom, time_to: state.filters.timeTo })
      .then(setData)
      .catch(fail);
  }, [ids, bucket, types, compact, state.filters.timeFrom, state.filters.timeTo, fail]);

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);

  useEffect(() => {
    const c = chart.current;
    if (!c || !data) return;
    const etypes = Object.keys(data.by_type).sort();
    const color = (t: string) => PALETTE[etypes.indexOf(t) % PALETTE.length];
    const bars = etypes.map((t) => ({
      name: t, type: "bar", stack: "h", xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 18, itemStyle: { color: color(t) },
      data: data.histogram.series.map((s) => [s.t, s.counts[t] ?? 0]),
    }));
    // open the zoom window on the dense part of the data (5th–100th percentile) so a few old events don't flatten the view
    const times = data.events.map((e) => Date.parse(e.timestamp)).sort((a, b) => a - b);
    const startValue = times.length > 20 ? times[Math.floor(times.length * 0.05)] : undefined;
    const scatter = {
      name: "events", type: "scatter", xAxisIndex: 1, yAxisIndex: 1, symbolSize: 6,
      data: data.events.map((e) => ({ value: [e.timestamp, e.event_type], id: e.id, itemStyle: { color: color(e.event_type) } })),
    };
    c.setOption({
      backgroundColor: "transparent",
      animation: false,
      textStyle: { color: "#9aa5b8", fontSize: 10 },
      tooltip: { trigger: "item", backgroundColor: "#141922", borderColor: "#2f3a4b", textStyle: { color: "#e3e8ef", fontSize: 11 },
                 formatter: (p: any) => (p.seriesName === "events" ? `${p.value[1]}<br/>${fmtTime(p.value[0])}` : `${p.seriesName}: ${p.value[1]}<br/>${fmtTime(p.value[0])}`) },
      legend: compact ? { show: false } : { top: 0, textStyle: { color: "#9aa5b8", fontSize: 10 }, itemWidth: 10, itemHeight: 8, data: etypes },
      grid: compact ? [{ left: 118, right: 12, top: 8, height: "40%" }, { left: 118, right: 12, top: "58%", bottom: 36 }]
                    : [{ left: 50, right: 20, top: 30, height: "30%" }, { left: 120, right: 20, top: "48%", bottom: 50 }],
      xAxis: [
        { type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: "#2f3a4b" } } },
        { type: "time", gridIndex: 1, axisLine: { lineStyle: { color: "#2f3a4b" } }, splitLine: { show: true, lineStyle: { color: "#161d28" } } },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, splitLine: { lineStyle: { color: "#161d28" } } },
        { type: "category", gridIndex: 1, data: etypes, axisLine: { lineStyle: { color: "#2f3a4b" } } },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], filterMode: "weakFilter", startValue },
        { type: "slider", xAxisIndex: [0, 1], height: 14, bottom: 6, borderColor: "#2f3a4b", textStyle: { color: "#6f7b8f" }, filterMode: "weakFilter", startValue },
      ],
      series: [...bars, scatter],
    }, true);
    c.off("click");
    c.on("click", (p: any) => { if (p.seriesName === "events" && p.data?.id) dispatch({ type: "SELECT", selection: { kind: "event", id: p.data.id } }); });
    c.off("datazoom");
    c.on("datazoom", () => {
      const opt: any = c.getOption();
      const dz = opt.dataZoom?.[0];
      if (dz?.startValue != null && dz?.endValue != null) setZoomWindow([new Date(dz.startValue).toISOString(), new Date(dz.endValue).toISOString()]);
    });
  }, [data, compact, dispatch]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-ink-800 bg-ink-900 px-2 text-2xs text-ink-400">
        <span>{ids.length ? `${ids.length} workspace entities` : "all events"} · {data?.total ?? 0} events · span {fmtTime(data?.span.from)} → {fmtTime(data?.span.to)}</span>
        <select value={bucket} onChange={(e) => setBucket(e.target.value as any)} className="ml-2 h-5 rounded-sm border border-ink-600 bg-ink-850 px-1" aria-label="Bucket">
          <option value="hour">hour</option><option value="day">day</option><option value="week">week</option>
        </select>
        {!compact && data && (
          <select className="h-5 rounded-sm border border-ink-600 bg-ink-850 px-1" value={types?.[0] ?? ""} onChange={(e) => setTypes(e.target.value ? [e.target.value] : null)} aria-label="Event type">
            <option value="">all event types</option>
            {Object.keys(data.by_type).sort().map((t) => <option key={t} value={t}>{t} ({data.by_type[t]})</option>)}
          </select>
        )}
        {zoomWindow && (
          <Button className="ml-2" onClick={() => dispatch({ type: "SET_FILTERS", filters: { timeFrom: zoomWindow[0], timeTo: zoomWindow[1] } })}>
            Apply {fmtTime(zoomWindow[0]).slice(0, 16)} → {fmtTime(zoomWindow[1]).slice(0, 16)} as time filter
          </Button>
        )}
        {(state.filters.timeFrom || state.filters.timeTo) && (
          <Button variant="ghost" onClick={() => dispatch({ type: "SET_FILTERS", filters: { timeFrom: null, timeTo: null } })}>Clear time filter</Button>
        )}
        {data && data.simultaneous.groups.length > 0 && <span className="ml-auto text-signal">{data.simultaneous.groups.length} simultaneous-event group(s) (≤{data.simultaneous.window_seconds}s)</span>}
      </div>
      <div ref={ref} className="flex-1" data-testid="timeline-chart" />
      {!compact && data && (
        <div className="h-40 shrink-0 overflow-auto border-t border-ink-800">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-ink-850 text-2xs uppercase text-ink-400">
              <tr><th className="px-2 text-left">Time</th><th className="text-left">Event</th><th className="text-left">Source</th><th className="text-left">Entities</th><th className="text-left">Status</th></tr>
            </thead>
            <tbody>
              {data.events.slice(0, 500).map((e) => (
                <tr key={e.id} className="cursor-pointer border-b border-ink-800 hover:bg-ink-800" onClick={() => dispatch({ type: "SELECT", selection: { kind: "event", id: e.id } })}>
                  <td className="px-2 font-mono text-2xs">{fmtTime(e.timestamp)}</td><td>{e.event_type}</td><td className="text-ink-400">{e.source}</td>
                  <td className="text-ink-400">{e.entity_ids.length}</td><td className="text-2xs text-ink-400">{e.epistemic_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
