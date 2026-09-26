import { useCallback } from "react";
import { api, ApiError } from "../api/client";
import { useStore } from "./context";

/** Workspace operations shared by the command bar, graph, entity panels and investigations. */
export function useActions() {
  const { state, dispatch } = useStore();

  const fail = useCallback((e: unknown) => {
    dispatch({ type: "TOAST", level: "error", text: e instanceof ApiError ? `${e.status}: ${e.message}` : String(e) });
  }, [dispatch]);

  const expand = useCallback(
    async (ids: string[], depth = 1) => {
      try {
        const f = state.filters;
        const g = await api.subgraph(ids, depth, {
          relationship_types: f.relationshipTypes,
          time_from: f.timeFrom,
          time_to: f.timeTo,
          min_confidence: f.minConfidence,
        });
        dispatch({ type: "ADD_GRAPH", nodes: g.nodes, edges: g.edges });
        if (g.truncated) dispatch({ type: "TOAST", level: "info", text: `Partial view: ${g.truncation_reasons?.[0] ?? "limits reached"}` });
        return g;
      } catch (e) {
        fail(e);
      }
    },
    [dispatch, fail, state.filters],
  );

  const addEntity = useCallback(
    async (id: string, select = true) => {
      try {
        const g = await api.subgraph([id], 0);
        dispatch({ type: "ADD_GRAPH", nodes: g.nodes, edges: [] });
        if (select) dispatch({ type: "SELECT", selection: { kind: "entity", id: g.nodes[0]?.id ?? id } });
      } catch (e) {
        fail(e);
      }
    },
    [dispatch, fail],
  );

  const pin = useCallback(
    async (kind: string, ref_id: string, title: string, content: Record<string, unknown> = {}) => {
      if (!state.investigationId) {
        dispatch({ type: "TOAST", level: "info", text: "Open or create an investigation first (Investigation tab)." });
        return;
      }
      try {
        await api.addItem(state.investigationId, { kind, ref_id, title, content });
        dispatch({ type: "TOAST", level: "info", text: `Pinned ${kind} to investigation` });
      } catch (e) {
        fail(e);
      }
    },
    [dispatch, fail, state.investigationId],
  );

  return { expand, addEntity, pin, fail };
}
