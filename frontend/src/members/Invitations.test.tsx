import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/* Invitations: create, link shown once, revoke, confirm the role (Q4, Q5). */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const JOINED = "dddddddd-0000-4000-8000-000000000004";
const PENDING_ID = "eeeeeeee-0000-4000-8000-000000000005";
const ACCEPTED_ID = "ffffffff-0000-4000-8000-000000000006";
const TOKEN = "made-up-token-for-tests-only-0123456789abcdef"; // pragma: allowlist secret
const LINK = `http://localhost:8000/app/invite/${WS}#${TOKEN}`;
const stamp = "2026-10-24T09:00:00+00:00";

const ADMIN = {
  read_members: true,
  assign_role: true,
  remove_role: true,
  suspend_member: true,
  reactivate_member: true,
  revoke_member: true,
  manage_owners: false,
  read_invitations: true,
  create_invitation: true,
  revoke_invitation: true,
};

function invitation(id: string, email: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    email,
    role: "Member",
    delivery: "manual",
    status,
    invited_by_user_id: "u-me",
    created_at: stamp,
    expires_at: "2026-10-31T09:00:00+00:00",
    accepted_by_user_id: null,
    ...extra,
  };
}

function team(actions: Record<string, boolean>, overrides: Handler = () => undefined): Handler {
  return (method, path, body) => {
    const custom = overrides(method, path, body);
    if (custom) return custom;
    if (method !== "GET") return undefined;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: ME, roles: ["Admin"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return {
        status: 200,
        body: {
          items: [
            { membership_id: ME, user_id: "u-me", status: "active", roles: ["Admin"] },
            { membership_id: JOINED, user_id: "u-new", status: "active", roles: [] },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        },
      };
    }
    if (path === `/v1/workspaces/${WS}/invitations`) {
      return {
        status: 200,
        body: {
          items: [
            invitation(PENDING_ID, "pending@example.test", "pending"),
            invitation(ACCEPTED_ID, "joined@example.test", "accepted", { accepted_by_user_id: "u-new" }),
          ],
        },
      };
    }
    return undefined;
  };
}

const openTeam = (handler: Handler) => renderApp(`/w/${WS}/settings`, handler);

afterEach(() => {
  sessionStorage.clear();
});

describe("inviting members", () => {
  it("creates a manual invitation and shows its link once, labelled not sent", async () => {
    const user = userEvent.setup();
    const { sent } = openTeam(
      team(ADMIN, (method, path) =>
        method === "POST" && path === `/v1/workspaces/${WS}/invitations`
          ? {
              status: 201,
              body: { invitation: invitation("new-id", "new@example.test", "pending"), link: LINK },
            }
          : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Invite" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite a member" });
    const role = within(dialog).getByLabelText("Role after joining");
    // An Admin cannot invite an Owner.
    expect(within(role).queryByRole("option", { name: "Owner" })).toBeNull();
    await user.type(within(dialog).getByLabelText(/Email address/), "new@example.test");
    await user.selectOptions(role, "Read-only");
    await user.click(within(dialog).getByRole("button", { name: /Create invitation/ }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toEqual([
        {
          method: "POST",
          path: `/v1/workspaces/${WS}/invitations`,
          body: { email: "new@example.test", role: "Read-only" },
        },
      ]);
    });
    const shown = await screen.findByRole("dialog", { name: "Invitation link" });
    expect(within(shown).getByText(/Not sent — deliver it yourself/)).toBeInTheDocument();
    expect(within(shown).getByLabelText("Invitation link")).toHaveValue(LINK);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(shown).getByRole("button", { name: "Done" }));
    expect(screen.queryByDisplayValue(LINK)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("explains a refused invitation", async () => {
    const user = userEvent.setup();
    openTeam(
      team(ADMIN, (method) =>
        method === "POST" ? { status: 409, body: { detail: { code: "duplicate_invitation" } } } : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Invite" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite a member" });
    await user.type(within(dialog).getByLabelText(/Email address/), "pending@example.test");
    await user.click(within(dialog).getByRole("button", { name: /Create invitation/ }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/already has a pending invitation/);
  });

  it("lists pending invitations and revokes one after confirmation", async () => {
    const user = userEvent.setup();
    const { sent } = openTeam(
      team(ADMIN, (method, path) =>
        method === "POST" && path === `/v1/workspaces/${WS}/invitations/${PENDING_ID}/revoke`
          ? { status: 200, body: invitation(PENDING_ID, "pending@example.test", "revoked") }
          : undefined,
      ),
    );
    const card = await screen.findByRole("region", { name: "Invitations" });
    expect(await within(card).findByText("pending@example.test")).toBeInTheDocument();
    expect(within(card).queryByText("joined@example.test")).toBeNull(); // accepted ones are members
    await user.click(within(card).getByRole("button", { name: "Revoke" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Revoke invitation?" });
    await user.click(within(confirm).getByRole("button", { name: "Revoke" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST").map((r) => r.path)).toEqual([
        `/v1/workspaces/${WS}/invitations/${PENDING_ID}/revoke`,
      ]);
    });
  });

  it("shows a joined member as awaiting role and confirms the invited role in one action", async () => {
    const user = userEvent.setup();
    const { sent } = openTeam(
      team(ADMIN, (method, path) =>
        method === "POST" && path === `/v1/workspaces/${WS}/members/${JOINED}/roles`
          ? { status: 200, body: { membership_id: JOINED, user_id: "u-new", status: "active", roles: ["Member"] } }
          : undefined,
      ),
    );
    const row = (await screen.findByText("joined@example.test")).closest("li");
    if (!row) throw new Error("row not found");
    expect(within(row).getByText("Awaiting role")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Give Member role" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST").map((r) => [r.path, r.body])).toEqual([
        [`/v1/workspaces/${WS}/members/${JOINED}/roles`, expect.objectContaining({ role: "Member" })],
      ]);
    });
  });

  it("offers members who may not invite no invitation controls", async () => {
    openTeam(team({ read_members: true }));
    expect(await screen.findByText("2 members")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Invite" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Invitations" })).toBeNull();
  });
});
