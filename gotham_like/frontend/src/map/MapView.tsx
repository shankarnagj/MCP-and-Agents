import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { EventItem } from "../api/types";
import { Button, fmtTime } from "../components/ui";
import { TYPE_COLORS } from "../graph/elements";
import { useActions } from "../state/actions";
import { useStore } from "../state/context";
import { visibleNodes } from "../state/store";

const EVENT_COLORS: Record<string, string> = {
  transaction: "#9d8cff", login: "#57d3c1", logout: "#4a8f86", auth_failure: "#e5534b", device_connection: "#4ea1ff", location_change: "#f0b35e",
  dns_query: "#e67fb8", shipment_departure: "#d6c35a", shipment_arrival: "#7fd46a", account_opened: "#8b98ad", communication: "#b0b0b0",
};

/** Offline-first style: no external tiles or glyphs. A graticule gives spatial reference. */
function graticule(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (let lon = -180; lon <= 180; lon += 5) features.push({ type: "Feature", properties: { major: lon % 30 === 0 }, geometry: { type: "LineString", coordinates: [[lon, -85], [lon, 85]] } });
  for (let lat = -80; lat <= 80; lat += 5) features.push({ type: "Feature", properties: { major: lat % 30 === 0 }, geometry: { type: "LineString", coordinates: [[-180, lat], [180, lat]] } });
  return { type: "FeatureCollection", features };
}

function circle(lon: number, lat: number, meters: number): GeoJSON.Feature {
  const pts: number[][] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    const dLat = (meters / 111320) * Math.sin(a);
    const dLon = (meters / (111320 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a);
    pts.push([lon + dLon, lat + dLat]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } };
}

const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });

export function MapView() {
  const { state, dispatch } = useStore();
  const { addEntity, pin, fail } = useActions();
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [heat, setHeat] = useState(false);
  const [radiusMode, setRadiusMode] = useState(false);
  const [radius, setRadius] = useState(2000);
  const [radiusResult, setRadiusResult] = useState<{ entities: any[]; events: EventItem[]; lat: number; lon: number } | null>(null);
  const modeRef = useRef({ radiusMode, radius });
  modeRef.current = { radiusMode, radius };

  const nodes = useMemo(() => visibleNodes(state).filter((n) => n.lat != null && n.lon != null), [state.nodes, state.filters]);
  const ids = useMemo(() => Object.keys(state.nodes), [state.nodes]);

  useEffect(() => {
    if (!ref.current) return;
    // VITE_MAP_STYLE_URL may point to a self-hosted MapLibre style (e.g. OpenMapTiles); default is fully offline.
    const styleUrl = import.meta.env.VITE_MAP_STYLE_URL as string | undefined;
    const m = new maplibregl.Map({
      container: ref.current,
      style: styleUrl ?? {
        version: 8,
        sources: { grat: { type: "geojson", data: graticule() } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0d1117" } },
          { id: "grat", type: "line", source: "grat", paint: { "line-color": ["case", ["get", "major"], "#243042", "#161d28"], "line-width": 1 } },
        ],
      },
      center: [20, 35],
      zoom: 1.6,
      attributionControl: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.on("load", () => {
      const empty = fc([]);
      m.addSource("heat", { type: "geojson", data: empty });
      m.addSource("fences", { type: "geojson", data: empty });
      m.addSource("radius", { type: "geojson", data: empty });
      m.addSource("traj", { type: "geojson", data: empty });
      m.addSource("events", { type: "geojson", data: empty, cluster: true, clusterRadius: 30, clusterMaxZoom: 13 });
      m.addSource("entities", { type: "geojson", data: empty });
      m.addLayer({ id: "heat", type: "heatmap", source: "heat", layout: { visibility: "none" },
        paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "count"], 0, 0, 50, 1], "heatmap-radius": 25, "heatmap-opacity": 0.75,
                 "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.3, "#2d5f99", 0.6, "#e0a341", 1, "#e5534b"] } });
      m.addLayer({ id: "fences-fill", type: "fill", source: "fences", paint: { "fill-color": "#b48cff", "fill-opacity": 0.08 } });
      m.addLayer({ id: "fences-line", type: "line", source: "fences", paint: { "line-color": "#b48cff", "line-width": 1.5, "line-dasharray": [2, 2] } });
      m.addLayer({ id: "radius-fill", type: "fill", source: "radius", paint: { "fill-color": "#4ea1ff", "fill-opacity": 0.07 } });
      m.addLayer({ id: "radius-line", type: "line", source: "radius", paint: { "line-color": "#4ea1ff", "line-width": 1 } });
      m.addLayer({ id: "traj", type: "line", source: "traj", paint: { "line-color": "#e0a341", "line-width": 1.5, "line-dasharray": [1, 1.5] } });
      m.addLayer({ id: "clusters", type: "circle", source: "events", filter: ["has", "point_count"],
        paint: { "circle-color": "#2f3a4b", "circle-stroke-color": "#6f7b8f", "circle-stroke-width": 1, "circle-radius": ["step", ["get", "point_count"], 10, 20, 14, 100, 18] } });
      m.addLayer({ id: "events", type: "circle", source: "events", filter: ["!", ["has", "point_count"]],
        paint: { "circle-color": ["coalesce", ["get", "color"], "#9aa5b8"], "circle-radius": 4, "circle-stroke-color": "#0b0e13", "circle-stroke-width": 1 } });
      m.addLayer({ id: "entities", type: "circle", source: "entities",
        paint: { "circle-color": ["get", "color"], "circle-radius": 6, "circle-stroke-color": ["case", ["get", "selected"], "#4ea1ff", "#0b0e13"], "circle-stroke-width": 2 } });
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
      for (const layer of ["events", "entities"]) {
        m.on("mouseenter", layer, (e) => {
          m.getCanvas().style.cursor = "pointer";
          const p = e.features?.[0]?.properties ?? {};
          popup.setLngLat(e.lngLat).setHTML(`<b>${escapeHtml(p.title ?? "")}</b><br/>${escapeHtml(p.sub ?? "")}`).addTo(m);
        });
        m.on("mouseleave", layer, () => { m.getCanvas().style.cursor = ""; popup.remove(); });
      }
      m.on("click", "entities", (e) => { const id = e.features?.[0]?.properties?.id; if (id) dispatch({ type: "SELECT", selection: { kind: "entity", id } }); });
      m.on("click", "events", (e) => { const id = e.features?.[0]?.properties?.id; if (id) dispatch({ type: "SELECT", selection: { kind: "event", id } }); });
      m.on("click", "clusters", (e) => m.easeTo({ center: e.lngLat, zoom: m.getZoom() + 2 }));
      m.on("click", (e) => { if (modeRef.current.radiusMode) radiusQuery(e.lngLat.lat, e.lngLat.lng); });
      api.geofences().then((g) => (m.getSource("fences") as GeoJSONSource).setData(g)).catch(() => undefined);
      setReady(true);
    });
    map.current = m;
    return () => m.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // events for workspace entities (time-filtered)
  useEffect(() => {
    if (!ids.length) { setEvents([]); return; }
    api.timeline({ entity_id: ids.slice(0, 150), time_from: state.filters.timeFrom, time_to: state.filters.timeTo, limit: 3000 })
      .then((t) => setEvents(t.events.filter((e) => e.lat != null)))
      .catch(fail);
  }, [ids, state.filters.timeFrom, state.filters.timeTo, fail]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const sel = state.selection?.kind === "entity" ? state.selection.id : null;
    (m.getSource("entities") as GeoJSONSource).setData(fc(nodes.map((n) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [n.lon!, n.lat!] },
      properties: { id: n.id, color: TYPE_COLORS[n.type] ?? "#999", title: n.label, sub: `${n.type} · ${n.epistemic_status}`, selected: n.id === sel },
    }))));
    const evs = [...events, ...(radiusResult?.events ?? [])];
    (m.getSource("events") as GeoJSONSource).setData(fc(evs.map((e) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [e.lon!, e.lat!] },
      properties: { id: e.id, color: EVENT_COLORS[e.event_type], title: e.event_type, sub: `${fmtTime(e.timestamp)} · ${e.source}` },
    }))));
  }, [nodes, events, radiusResult, ready, state.selection]);

  // trajectory of selected entity
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const src = m.getSource("traj") as GeoJSONSource;
    if (state.selection?.kind !== "entity") { src.setData(fc([])); return; }
    api.trajectory(state.selection.id).then((t) => src.setData(t.geometry.type === "LineString" ? fc([t]) : fc([]))).catch(() => src.setData(fc([])));
  }, [state.selection, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setLayoutProperty("heat", "visibility", heat ? "visible" : "none");
    if (heat) api.heatmap({ cell_deg: 0.02, time_from: state.filters.timeFrom, time_to: state.filters.timeTo }).then((h) => (m.getSource("heat") as GeoJSONSource).setData(h)).catch(fail);
  }, [heat, ready, state.filters.timeFrom, state.filters.timeTo, fail]);

  const fit = () => {
    const m = map.current;
    const pts = [...nodes.map((n) => [n.lon!, n.lat!]), ...events.map((e) => [e.lon!, e.lat!])];
    if (!m || !pts.length) return;
    const b = new maplibregl.LngLatBounds(pts[0] as [number, number], pts[0] as [number, number]);
    pts.forEach((p) => b.extend(p as [number, number]));
    m.fitBounds(b, { padding: 60, maxZoom: 14, duration: 0 });
  };

  const radiusQuery = async (lat: number, lon: number) => {
    const m = map.current;
    (m?.getSource("radius") as GeoJSONSource | undefined)?.setData(fc([circle(lon, lat, modeRef.current.radius)]));
    try {
      const r = await api.geoQuery({ lat, lon, radius_m: modeRef.current.radius, time_from: state.filters.timeFrom, time_to: state.filters.timeTo, limit: 500 });
      setRadiusResult({ entities: r.entities ?? [], events: (r.events ?? []).filter((e: EventItem) => e.lat != null), lat, lon });
    } catch (e) {
      fail(e);
    }
  };

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex h-8 shrink-0 items-center gap-1 border-b border-ink-800 bg-ink-900 px-2 text-2xs">
        <Button onClick={fit}>Fit to data</Button>
        <Button variant={heat ? "primary" : "default"} onClick={() => setHeat(!heat)}>Heatmap</Button>
        <Button title="Save this map view (centre, zoom, filters, entities) to the active investigation"
          onClick={() => { const m = map.current; if (!m) return; const c = m.getCenter();
            pin("map", null, `Map view @ ${c.lat.toFixed(3)}, ${c.lng.toFixed(3)}`,
                { center: [c.lng, c.lat], zoom: m.getZoom(), filters: state.filters, entity_ids: Object.keys(state.nodes).slice(0, 500),
                  radius_query: radiusResult ? { lat: radiusResult.lat, lon: radiusResult.lon, radius_m: radius } : null }); }}>
          Pin view
        </Button>
        <Button variant={radiusMode ? "primary" : "default"} onClick={() => setRadiusMode(!radiusMode)}>Radius query</Button>
        <input type="number" value={radius} min={50} max={500000} step={100} onChange={(e) => setRadius(Number(e.target.value))} className="h-6 w-20 rounded-sm border border-ink-600 bg-ink-850 px-1" aria-label="Radius (m)" />
        <span className="text-ink-400">m {radiusMode && "— click the map"}</span>
        <span className="ml-auto text-ink-400">
          {nodes.length} located entities · {events.length} events {state.filters.timeFrom || state.filters.timeTo ? `· ${fmtTime(state.filters.timeFrom)} → ${fmtTime(state.filters.timeTo)}` : ""}
        </span>
      </div>
      <div ref={ref} className="flex-1" data-testid="map" />
      {radiusResult && (
        <div className="absolute right-2 top-10 max-h-[60%] w-72 overflow-auto rounded-sm border border-ink-600 bg-ink-900/95 text-xs">
          <div className="flex items-center justify-between border-b border-ink-700 px-2 py-1">
            <span className="text-2xs uppercase tracking-wider text-ink-400">Within {radius} m · {radiusResult.entities.length} entities · {radiusResult.events.length} events</span>
            <button className="text-ink-400" onClick={() => { setRadiusResult(null); (map.current?.getSource("radius") as GeoJSONSource)?.setData(fc([])); }}>×</button>
          </div>
          {radiusResult.entities.slice(0, 100).map((e) => (
            <div key={e.id} className="flex cursor-pointer items-center gap-2 px-2 py-[2px] hover:bg-ink-800" onClick={() => addEntity(e.id)}>
              <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLORS[e.type] }} />
              <span className="truncate">{e.label}</span>
              <span className="ml-auto font-mono text-2xs text-ink-400">{Math.round(e.distance_m ?? 0)} m</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function escapeHtml(s: string) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
