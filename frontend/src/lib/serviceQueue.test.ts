import { afterEach, describe, expect, it, vi } from "vitest";
import { queuedOperation, queueSnapshot, rememberBarKeys, forgetBarKeys, waitForService } from "@/lib/serviceQueue";

function ticket(state: string, position = 1) {
  return new Response(JSON.stringify({ id: "ticket1", state, position, expires_in: 60 }), { status: 200 });
}
function browser() {
  vi.stubGlobal("window", { location: { pathname: "/conversations", assign: vi.fn() }, addEventListener: vi.fn(), removeEventListener: vi.fn() });
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("fair queue browser reservations", () => {
  it("polls every two seconds, publishes position and never sends API keys", async () => {
    browser(); vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(ticket("waiting", 3)).mockResolvedValueOnce(ticket("ready"));
    vi.stubGlobal("fetch", fetch);
    const waiting = waitForService("call", "/api/offer", { target: "conversation1" });
    await vi.advanceTimersByTimeAsync(0);
    expect(queueSnapshot()[0].position).toBe(3);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ kind: "call", resource: "/api/offer", target: "conversation1" });
    await vi.advanceTimersByTimeAsync(1999);
    expect(fetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect((await waiting).ticket).toBe("ticket1");
    expect(queueSnapshot()).toEqual([]);
  });

  it("cancels the server ticket and clears the waiting notice", async () => {
    browser(); vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(ticket("waiting", 2)).mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const outcome = waitForService("turn", "/api/conversations/c1/turns").catch((e: Error) => e);
    await vi.advanceTimersByTimeAsync(0);
    queueSnapshot()[0].cancel();
    await vi.advanceTimersByTimeAsync(0);
    expect(await outcome).toMatchObject({ message: "已取消排队" });
    expect(fetch.mock.calls[1][0]).toBe("/api/queue/ticket1");
    expect(fetch.mock.calls[1][1].method).toBe("DELETE");
    expect(queueSnapshot()).toEqual([]);
  });

  it("bypasses only when the caller identifies own main services", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    expect((await waitForService("turn", "/api/conversations/c1/turns", { bypass: true })).ticket).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    expect(queuedOperation("/api/conversations/c1/turns", { method: "POST", body: JSON.stringify({ own_keys: { llm: {} } }) })).toEqual({ kind: "turn", bypass: true });
    expect(queuedOperation("/api/conversations/c1/turns", { method: "POST", body: JSON.stringify({ own_keys: { tts: {} } }) })).toEqual({ kind: "turn", bypass: false });
    expect(queuedOperation("/api/queue", { method: "POST" })).toBeNull();
    rememberBarKeys("visit1", true);
    expect(queuedOperation("/api/bar/visits/visit1/serves", { method: "POST" })).toEqual({ kind: "bar", bypass: true });
    forgetBarKeys("visit1");
    expect(queuedOperation("/api/bar/visits/visit1/serves", { method: "POST" })).toEqual({ kind: "bar", bypass: false });
  });

  it("reports expired tickets instead of submitting the original operation", async () => {
    browser(); vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(ticket("waiting", 2)).mockResolvedValue(new Response(JSON.stringify({ detail: "请重新排队", code: "queue_expired" }), { status: 410 }));
    vi.stubGlobal("fetch", fetch);
    const outcome = waitForService("turn", "/api/conversations/c1/turns").catch((e: Error) => e);
    await vi.advanceTimersByTimeAsync(2000);
    expect(await outcome).toMatchObject({ message: "请重新排队" });
    expect(queueSnapshot()).toEqual([]);
  });
});
