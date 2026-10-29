import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const OTHER_OWNER = "bbbbbbbb-0000-4000-8000-000000000002";
const MEMBER = "cccccccc-0000-4000-8000-000000000003";
const ALL = {
  read_members: true,
  assign_role: true,
  remove_role: true,
  suspend_member: true,
  reactivate_member: true,
  revoke_member: true,
  manage_owners: true,
};

function workspace(access: { roles: string[]; actions: Record<string, boolean> }): Handler {
  return (method, path) => {
    if (method !== "GET") return undefined;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) {
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    }
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: ME, ...access } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return {
        status: 200,
        body: {
          items: [
            { membership_id: ME, user_id: "u-me", status: "active", roles: access.roles },
            { membership_id: OTHER_OWNER, user_id: "u-2", status: "active", roles: ["Owner"] },
            { membership_id: MEMBER, user_id: "u-3", status: "active", roles: ["Member"] },
          ],
          total: 3,
          limit: 50,
          offset: 0,
        },
      };
    }
    return undefined;
  };
}

const rowFor = (id: string) => {
  const row = screen.getByText(`Member ${id.slice(0, 8)}`).closest("li");
  if (!row) throw new Error("row not found");
  return row;
};

describe("workspace members", () => {
  it("lists members with roles and status, and passes an accessibility scan", async () => {
    renderApp(`/w/${WS}/settings`, workspace({ roles: ["Owner"], actions: ALL }));
    expect(await screen.findByRole("heading", { name: "Team & roles" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /^Acme/ })).toBeInTheDocument();
    expect(await screen.findByText("3 members")).toBeInTheDocument();
    expect(within(rowFor(ME)).getByText("You")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("offers an Admin no action on an Owner", async () => {
    renderApp(
      `/w/${WS}/settings`,
      workspace({ roles: ["Admin"], actions: { ...ALL, manage_owners: false } }),
    );
    await screen.findByText("3 members");
    expect(within(rowFor(OTHER_OWNER)).queryByRole("button")).toBeNull();
    expect(
      within(rowFor(MEMBER)).getByRole("button", { name: /Actions for member/ }),
    ).toBeVisible();
  });

  it("confirms an Owner change before sending it, with the confirmation flag", async () => {
    const user = userEvent.setup();
    const base = workspace({ roles: ["Owner"], actions: ALL });
    const { sent } = renderApp(`/w/${WS}/settings`, (method, path, body) =>
      method === "POST" ? { status: 200, body: {} } : base(method, path, body),
    );
    await screen.findByText("3 members");
    await user.click(within(rowFor(MEMBER)).getByRole("button", { name: /Actions for member/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Add role: Owner" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(sent.filter((r) => r.method === "POST")).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toEqual([
        {
          method: "POST",
          path: `/v1/workspaces/${WS}/members/${MEMBER}/roles`,
          body: { role: "Owner", confirm_owner_change: true },
        },
      ]);
    });
    expect(await screen.findByText("Change saved.")).toBeInTheDocument();
  });

  it("keeps keyboard focus on the page when a removed member's row disappears", async () => {
    const user = userEvent.setup();
    let revoked = false;
    const base = workspace({ roles: ["Owner"], actions: ALL });
    renderApp(`/w/${WS}/settings`, (method, path, body) => {
      if (method === "POST" && path.endsWith(`/members/${MEMBER}/revoke`)) {
        revoked = true;
        return { status: 200, body: {} };
      }
      const reply = base(method, path, body);
      if (revoked && reply && path.includes("/members?")) {
        const page = reply.body as { items: { membership_id: string }[]; total: number };
        const items = page.items.filter((m) => m.membership_id !== MEMBER);
        return { status: 200, body: { ...page, items, total: items.length } };
      }
      return reply;
    });
    await screen.findByText("3 members");
    await user.click(within(rowFor(MEMBER)).getByRole("button", { name: /Actions for member/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Remove from workspace" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("2 members")).toBeInTheDocument();
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByText("Change saved.").parentElement);
    });
  });

  it("leaves the workspace page on sign-out so none of its data stays on screen", async () => {
    const user = userEvent.setup();
    let signedOut = false;
    const base = workspace({ roles: ["Owner"], actions: ALL });
    renderApp(`/w/${WS}/settings`, (method, path, body) => {
      if (method === "POST" && path === "/auth/logout") {
        signedOut = true;
        return { status: 204 };
      }
      if (signedOut) return { status: 401, body: { detail: "Not authenticated" } };
      return base(method, path, body);
    });
    await screen.findByText("3 members");
    await user.click(screen.getByRole("button", { name: "Your account" }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in to LeadStack" })).toBeVisible();
    expect(screen.queryByText("Acme")).toBeNull();
    expect(screen.queryByText("3 members")).toBeNull();
  });

  it("shows the server's refusal when the last Owner would be removed", async () => {
    const user = userEvent.setup();
    const base = workspace({ roles: ["Owner"], actions: ALL });
    renderApp(`/w/${WS}/settings`, (method, path, body) =>
      method === "DELETE"
        ? { status: 409, body: { detail: { code: "last_owner" } } }
        : base(method, path, body),
    );
    await screen.findByText("3 members");
    await user.click(within(rowFor(ME)).getByRole("button", { name: /Actions for member/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Step down as Owner" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(
      await screen.findByText("The workspace must keep at least one active Owner."),
    ).toBeInTheDocument();
  });

  it("does not say whether a workspace it cannot open exists", async () => {
    renderApp(`/w/${WS}/settings`, (_, path) =>
      path === "/auth/me" ? { status: 200, body: { user_id: "u" } } : undefined,
    );
    expect(
      await screen.findByText("This workspace does not exist, or you are not a member of it."),
    ).toBeInTheDocument();
  });

  it("does not request anything for a malformed workspace ID", async () => {
    const { sent } = renderApp("/w/not-an-id", () => undefined);
    expect(
      await screen.findByText("This workspace does not exist, or you are not a member of it."),
    ).toBeInTheDocument();
    expect(sent.filter((r) => r.path.startsWith("/v1/"))).toEqual([]);
  });

  it("asks a signed-out visitor to sign in again", async () => {
    renderApp(`/w/${WS}/settings`, () => ({ status: 401, body: { detail: "Not authenticated" } }));
    expect(
      await screen.findByText("Your session has ended. Sign in again to continue."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Sign in" })[0]).toHaveAttribute(
      "href",
      "/auth/login",
    );
  });
});
