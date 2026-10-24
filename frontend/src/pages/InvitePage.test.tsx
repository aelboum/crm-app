import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/* Accepting an invitation link (decisions Q4, Q5; SaaS-OS ADR-0046). */

const WS = "11111111-2222-4333-8444-555555555555";
const TOKEN = "made-up-token-for-tests-only-0123456789abcdef"; // pragma: allowlist secret
const ACCEPT = `/v1/tenants/${WS}/invitations/accept`;

const signedIn = (overrides: Handler = () => undefined): Handler => (method, path, body) =>
  overrides(method, path, body) ??
  (path === "/auth/me" ? { status: 200, body: { user_id: "u-new" } } : undefined);

/** Opens the link as a browser would: the token in the fragment. */
function openLink(handler: Handler, withToken = true) {
  globalThis.history.replaceState(null, "", `/app/invite/${WS}${withToken ? `#${TOKEN}` : ""}`);
  return renderApp(`/invite/${WS}`, handler);
}

afterEach(() => {
  sessionStorage.clear();
  globalThis.history.replaceState(null, "", "/");
});

describe("accepting an invitation", () => {
  it("keeps the link through sign-in and clears it from the address bar", async () => {
    openLink(() => ({ status: 401, body: { detail: "Not authenticated" } }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/auth/login");
    expect(globalThis.location.hash).toBe("");
    expect(sessionStorage.getItem("crm.pendingInvitation")).toContain(TOKEN);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("accepts for the signed-in person and forgets the token", async () => {
    const user = userEvent.setup();
    const { sent } = openLink(
      signedIn((method, path) =>
        method === "POST" && path === ACCEPT ? { status: 200, body: { tenant_id: WS, status: "active" } } : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByText(/still needs to give you a role/)).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "POST")).toEqual([{ method: "POST", path: ACCEPT, body: { token: TOKEN } }]);
    expect(sessionStorage.getItem("crm.pendingInvitation")).toBeNull();
  });

  it("says only that a refused invitation cannot be used", async () => {
    const user = userEvent.setup();
    openLink(
      signedIn((method, path) =>
        method === "POST" && path === ACCEPT ? { status: 404, body: { detail: "invitation not found." } } : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot be used/);
  });

  it("explains an incomplete link", async () => {
    openLink(signedIn(), false);
    expect(await screen.findByText(/link is incomplete/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept invitation" })).toBeNull();
  });

  it("brings the person back to a waiting invitation after sign-in", async () => {
    sessionStorage.setItem("crm.pendingInvitation", JSON.stringify({ workspaceId: WS, token: TOKEN }));
    const { router } = renderApp("/", (_method, path) => {
      if (path === "/auth/me") return { status: 200, body: { user_id: "u-new" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      return undefined;
    });
    expect(await screen.findByText("You have an invitation waiting.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("link", { name: "Continue" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/invite/${WS}`);
    });
    expect(await screen.findByRole("button", { name: "Accept invitation" })).toBeInTheDocument();
  });
});
