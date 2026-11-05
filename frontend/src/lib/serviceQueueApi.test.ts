import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("queued business requests", () => {
  it("consumes a ready ticket on the original request without sharing its body with the queue", async () => {
    vi.stubGlobal("window", { location: { pathname: "/conversation/c1", assign: vi.fn() }, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({ id: "ticket1", state: "ready", position: 0, expires_in: 15 })).mockResolvedValueOnce(new Response("data: {}\n\n"));
    vi.stubGlobal("fetch", fetch);
    await api("/api/conversations/c1/turns", { method: "POST", body: JSON.stringify({ text: "hello" }) });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ kind: "turn", resource: "/api/conversations/c1/turns" });
    expect(new Headers(fetch.mock.calls[1][1].headers).get("x-queue-ticket")).toBe("ticket1");
    expect(fetch.mock.calls[1][1].body).toBe(JSON.stringify({ text: "hello" }));
  });

  it("sends BYOK operations directly with actual keys in the business request only", async () => {
    vi.stubGlobal("window", { location: { pathname: "/conversation/c1", assign: vi.fn() } });
    const fetch = vi.fn().mockResolvedValue(new Response("data: {}\n\n"));
    vi.stubGlobal("fetch", fetch);
    await api("/api/conversations/c1/turns", { method: "POST", body: JSON.stringify({ own_keys: { llm: { api_key: "secret" } } }) });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/conversations/c1/turns");
  });

  it("redirects expired password grants to the password entry, preserving the local destination", async () => {
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { pathname: "/settings/sign-in", search: "?source=test", assign } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ code: "access_required", detail: "请先验证" }, { status: 403 })));
    await api("/api/account");
    expect(assign).toHaveBeenCalledWith("/access?returnTo=%2Fsettings%2Fsign-in%3Fsource%3Dtest");
  });
});
