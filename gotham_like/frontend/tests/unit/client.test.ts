import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, auth, formatDetail, onUnauthorized } from "../../src/api/client";

afterEach(() => { vi.restoreAllMocks(); auth.token = null; });

describe("api client", () => {
  it("sends the bearer token and parses JSON", async () => {
    auth.token = "tok";
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ id: "u", username: "a", role: "ANALYST", permissions: [] }), { status: 200 }));
    const me = await api.me();
    expect(me.username).toBe("a");
    expect((f.mock.calls[0][1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer tok" });
  });
  it("clears the token and notifies on 401", async () => {
    auth.token = "tok";
    const cb = vi.fn();
    const off = onUnauthorized(cb);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Session expired or revoked" }), { status: 401 }));
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(auth.token).toBeNull();
    expect(cb).toHaveBeenCalled();
    off();
  });
  it("formats validation errors", () => {
    expect(formatDetail([{ msg: "a" }, { msg: "b" }])).toBe("a; b");
    expect(formatDetail("x")).toBe("x");
  });
});
