/** WebSocket connection: live alerts, investigation updates, collaborative presence, long-running progress. */
import { auth } from "../api/client";

export interface WsMessage {
  topic: string;
  event: string;
  payload: Record<string, any>;
  ts: string;
}

type Handler = (m: WsMessage) => void;

let socket: WebSocket | null = null;
const handlers = new Map<string, Set<Handler>>();
const pending: string[] = [];
let retry = 0;

function send(obj: Record<string, unknown>) {
  const s = JSON.stringify(obj);
  if (socket?.readyState === WebSocket.OPEN) socket.send(s);
  else pending.push(s);
}

export function connect() {
  if (socket || !auth.token) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  socket = ws;
  ws.onopen = () => {
    retry = 0;
    ws.send(JSON.stringify({ type: "auth", token: auth.token })); // token in first frame, never in the URL
    for (const topic of handlers.keys()) if (topic !== "alerts") ws.send(JSON.stringify({ type: "subscribe", topic }));
    while (pending.length) ws.send(pending.shift()!);
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data) as WsMessage;
      handlers.get(msg.topic)?.forEach((h) => h(msg));
    } catch {
      /* ignore malformed */
    }
  };
  ws.onclose = () => {
    socket = null;
    if (auth.token && retry < 8) setTimeout(connect, Math.min(1000 * 2 ** retry++, 30000));
  };
}

export function disconnect() {
  retry = 99;
  socket?.close();
  socket = null;
}

export function on(topic: string, h: Handler): () => void {
  if (!handlers.has(topic)) {
    handlers.set(topic, new Set());
    if (topic !== "alerts") send({ type: "subscribe", topic });
  }
  handlers.get(topic)!.add(h);
  return () => handlers.get(topic)?.delete(h);
}

export function subscribeInvestigation(id: string, h: Handler): () => void {
  const topic = `investigation:${id}`;
  const off = on(topic, h);
  send({ type: "presence", topic, state: "viewing" });
  return off;
}
