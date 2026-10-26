import { afterEach, describe, expect, it, vi } from "vitest";

import { leaveAfterSignOut } from "./signOut";

const answer = (reply: () => Promise<Response>) => {
  vi.stubGlobal("fetch", vi.fn(reply));
};
const json = (body: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );

describe("leaveAfterSignOut", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("goes to the provider's end-session address when the server gives one", async () => {
    const url = "http://localhost:8000/oidc/v1/end_session?client_id=c";
    answer(() => json({ url }));
    const go = vi.fn();
    await leaveAfterSignOut(go);
    expect(go).toHaveBeenCalledWith(url);
  });

  it("uses an address fetched in advance, without asking again", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const go = vi.fn();
    await leaveAfterSignOut(go, Promise.resolve("http://localhost:8000/oidc/v1/end_session?client_id=c"));
    expect(go).toHaveBeenCalledWith("http://localhost:8000/oidc/v1/end_session?client_id=c");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("reloads the start page when none is configured", async () => {
    answer(() => json({ url: null }));
    const go = vi.fn();
    await leaveAfterSignOut(go);
    expect(go).toHaveBeenCalledWith("/app");
  });

  it("reloads the start page when the server cannot be reached", async () => {
    answer(() => Promise.reject(new TypeError("offline")));
    const go = vi.fn();
    await leaveAfterSignOut(go);
    expect(go).toHaveBeenCalledWith("/app");
  });
});
