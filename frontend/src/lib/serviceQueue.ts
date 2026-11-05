/** Browser reservations contain operation identifiers only; API keys stay in the actual request. */
import { api, json } from "@/lib/api";

export type QueueKind = "turn" | "call" | "bar" | "read_aloud";
export type QueueTicket = { id: string; state: "waiting" | "ready" | "running"; position: number; expires_in: number };
export type QueueNotice = { id: number; kind: QueueKind; position: number | null; cancel: () => void };

const EMPTY: readonly QueueNotice[] = [];
let snapshot: readonly QueueNotice[] = EMPTY;
let sequence = 0;
const notices = new Map<number, QueueNotice>();
const listeners = new Set<() => void>();
function publish() { snapshot = [...notices.values()]; for (const listener of listeners) listener(); }
export function subscribeQueue(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
export function queueSnapshot() { return snapshot; }
export function emptyQueueSnapshot() { return EMPTY; }

function pause(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const canceled = () => { clearTimeout(timer); reject(new Error("已取消排队")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", canceled); resolve(); }, 2000);
    signal.addEventListener("abort", canceled, { once: true });
    if (signal.aborted) canceled();
  });
}

export type Reservation = { ticket: string | null; cancelUnused: () => Promise<void> };

export async function waitForService(
  kind: QueueKind, resource: string,
  options: { bypass?: boolean; signal?: AbortSignal | null; target?: string } = {},
): Promise<Reservation> {
  if (options.bypass) return { ticket: null, cancelUnused: async () => {} };
  const controller = new AbortController();
  const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal;
  const id = ++sequence;
  let ticket: QueueTicket | null = null;
  const cancelUnused = async () => {
    if (!ticket) return;
    await api(`/api/queue/${encodeURIComponent(ticket.id)}`, { method: "DELETE", keepalive: true }).catch(() => {});
  };
  notices.set(id, { id, kind, position: null, cancel: () => controller.abort() });
  publish();
  const leaving = () => { controller.abort(); void cancelUnused(); };
  if (typeof window !== "undefined") window.addEventListener("pagehide", leaving, { once: true });
  try {
    ticket = await json<QueueTicket>(await api("/api/queue", {
      method: "POST", headers: { "content-type": "application/json" }, signal,
      body: JSON.stringify({ kind, resource, ...(options.target ? { target: options.target } : {}) }),
    }));
    while (ticket.state === "waiting") {
      notices.set(id, { id, kind, position: ticket.position, cancel: () => controller.abort() });
      publish();
      await pause(signal);
      ticket = await json<QueueTicket>(await api(`/api/queue/${encodeURIComponent(ticket.id)}`, { signal, cache: "no-store" }));
    }
    if (signal.aborted) throw new Error("已取消排队");
    if (ticket.state !== "ready") throw new Error("排队状态已变化，请重新排队");
    return { ticket: ticket.id, cancelUnused };
  } catch (e) {
    await cancelUnused();
    if (signal.aborted) throw new Error("已取消排队");
    throw e;
  } finally {
    if (typeof window !== "undefined") window.removeEventListener("pagehide", leaving);
    notices.delete(id); publish();
  }
}

/** Later bar replies use the keys held when that visit began, even if settings change. */
const ownBarVisits = new Set<string>();
export function rememberBarKeys(visit: string, own: boolean) { if (own) ownBarVisits.add(visit); else ownBarVisits.delete(visit); }
export function forgetBarKeys(visit: string) { ownBarVisits.delete(visit); }

export function queuedOperation(path: string, init: RequestInit): { kind: QueueKind; bypass: boolean } | null {
  if (init.method?.toUpperCase() !== "POST") return null;
  let own: { llm?: unknown; tts?: unknown } = {};
  if (typeof init.body === "string") {
    try { own = JSON.parse(init.body)?.own_keys ?? {}; } catch { /* backend validates malformed bodies */ }
  }
  if (/^\/api\/conversations\/[^/]+\/turns$/.test(path)) return { kind: "turn", bypass: !!own.llm };
  if (/^\/api\/conversations\/[^/]+\/(messages|reach-outs)\/[^/]+\/read-aloud$/.test(path)) return { kind: "read_aloud", bypass: !!own.tts };
  if (path === "/api/bar/visits") return { kind: "bar", bypass: !!own.llm };
  const visit = /^\/api\/bar\/visits\/([^/]+)\/(serves|retry)$/.exec(path);
  return visit ? { kind: "bar", bypass: ownBarVisits.has(decodeURIComponent(visit[1])) } : null;
}
