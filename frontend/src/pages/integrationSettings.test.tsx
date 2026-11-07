import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Settings › Integrations (decision P12-K): adding sends the name and a
 * Member or Read-only role; issuing a key shows it once, with how to use
 * it, and only until dismissed; revoking and disabling send the right
 * requests; members without the permission see no controls.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const URL = `/w/${WS}/settings?section=integrations`;
const ZAP = "a1000000-0000-4000-8000-000000000001";
const KEY = "b1000000-0000-4000-8000-000000000001";
const SECRET = "lsk_test_0123456789abcdef0123456789"; // pragma: allowlist secret
const stamp = "2026-11-07T09:30:00+00:00";

const INTEGRATION = {
  id: ZAP,
  name: "Zapier",
  status: "active",
  role: "Member",
  created_at: stamp,
  keys: [
    {
      id: KEY,
      name: "Production",
      created_at: stamp,
      expires_at: "2027-02-05T09:30:00+00:00",
      revoked_at: null,
    },
  ],
};

const HOOK = "c1000000-0000-4000-8000-000000000001";
const WEBHOOKS = {
  events: [
    "contact.created",
    "contact.updated",
    "deal.stage_changed",
    "form.submitted",
    "appointment.booked",
  ],
  items: [
    {
      id: HOOK,
      url: "https://hooks.example.org/in",
      created_at: stamp,
      deliveries: [
        {
          id: "d1",
          event: "contact.created",
          status: "published",
          attempts: 1,
          created_at: stamp,
          published_at: stamp,
          last_error: null,
        },
        {
          id: "d2",
          event: "deal.stage_changed",
          status: "dead_lettered",
          attempts: 8,
          created_at: stamp,
          published_at: null,
          last_error: "status 500",
        },
      ],
    },
  ],
};

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  canManage: boolean,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [canManage ? "Owner" : "Member"],
          actions: { manage_integrations: canManage, read_members: true },
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: { items: [], total: 0, limit: 50, offset: 0 },
      };
    }
    if (path === `${base}/integrations`) {
      return { status: 200, body: { items: [INTEGRATION] } };
    }
    if (path === `${base}/webhooks`) {
      return { status: 200, body: WEBHOOKS };
    }
    return undefined;
  };
}

describe("integration settings", () => {
  it("adds an integration as Read-only", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      URL,
      workspace(true, (method) =>
        method === "POST"
          ? { status: 201, body: { ...INTEGRATION, keys: [] } }
          : undefined,
      ),
    );
    const card = await screen.findByRole("region", { name: "Integrations" });
    expect(await within(card).findByText("Zapier")).toBeInTheDocument();
    await user.type(within(card).getByLabelText("Integration name"), "Sheets");
    await user.selectOptions(
      within(card).getByLabelText("Acts as"),
      "Read-only",
    );
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(
      within(card).getByRole("button", { name: "Add integration" }),
    );
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "POST",
        path: `/v1/workspaces/${WS}/integrations`,
        body: { name: "Sheets", role: "Read-only" },
      });
    });
  });

  it("shows a new key once, with how to use it, until dismissed", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      URL,
      workspace(true, (method, path) =>
        method === "POST" && path.endsWith("/keys")
          ? {
              status: 201,
              body: {
                key: { ...INTEGRATION.keys[0], id: "k2", name: "Spare" },
                secret: SECRET,
              },
            }
          : undefined,
      ),
    );
    const card = await screen.findByRole("region", { name: "Integrations" });
    await user.type(await within(card).findByLabelText("Key name"), "Spare");
    await user.selectOptions(within(card).getByLabelText("Expires"), "never");
    await user.click(within(card).getByRole("button", { name: "Issue key" }));
    const shown = await within(card).findByRole("status");
    expect(shown).toHaveTextContent("shown only once");
    expect(shown).toHaveTextContent(SECRET);
    expect(shown).toHaveTextContent("X-API-Key");
    expect(sent).toContainEqual({
      method: "POST",
      path: `/v1/workspaces/${WS}/integrations/${ZAP}/keys`,
      body: { name: "Spare", expires_in_days: null },
    });
    await user.click(
      within(card).getByRole("button", { name: "I have copied it" }),
    );
    expect(within(card).queryByText(SECRET)).toBeNull();
  });

  it("revokes a key and disables an integration after confirming", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      URL,
      workspace(true, (method, path) =>
        method === "POST" && path.endsWith("/revoke")
          ? { status: 204 }
          : method === "POST"
            ? { status: 200, body: { ...INTEGRATION, status: "disabled" } }
            : undefined,
      ),
    );
    const card = await screen.findByRole("region", { name: "Integrations" });
    await user.click(
      await within(card).findByRole("button", {
        name: "Revoke key Production",
      }),
    );
    await user.click(
      within(card).getByRole("button", { name: "Disable integration" }),
    );
    await user.click(
      within(card).getByRole("button", {
        name: "Disable Zapier and revoke its keys for good",
      }),
    );
    await waitFor(() => {
      expect(
        sent.filter((r) => r.method === "POST").map((r) => r.path),
      ).toEqual([
        `/v1/workspaces/${WS}/integrations/${ZAP}/keys/${KEY}/revoke`,
        `/v1/workspaces/${WS}/integrations/${ZAP}/disable`,
      ]);
    });
  });

  it("shows members without the permission no controls", async () => {
    renderApp(URL, workspace(false));
    const card = await screen.findByRole("region", { name: "Integrations" });
    expect(
      within(card).getByText("Only Owners and Admins can manage integrations."),
    ).toBeInTheDocument();
    expect(within(card).queryByRole("button")).toBeNull();
  });

  it("lists webhook deliveries and adds an address with its key once", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      URL,
      workspace(true, (method, path) =>
        method === "POST" && path.endsWith("/webhooks")
          ? {
              status: 201,
              body: {
                endpoint: { ...WEBHOOKS.items[0], deliveries: [] },
                signing_secret: SECRET,
              },
            }
          : method === "DELETE"
            ? { status: 204 }
            : undefined,
      ),
    );
    const hooks = await screen.findByRole("region", { name: "Webhooks" });
    const list = await within(hooks).findByRole("list", {
      name: "Recent deliveries to https://hooks.example.org/in",
    });
    expect(list).toHaveTextContent("contact.createdDelivered");
    expect(list).toHaveTextContent("Gave up");
    expect(list).toHaveTextContent("8 attempts");
    expect(list).toHaveTextContent("status 500");
    expect(hooks).toHaveTextContent("appointment.booked");
    await user.type(
      within(hooks).getByLabelText("HTTPS address"),
      "https://hooks.example.org/two",
    );
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(
      within(hooks).getByRole("button", { name: "Add address" }),
    );
    const shown = await within(hooks).findByRole("status");
    expect(shown).toHaveTextContent(SECRET);
    expect(shown).toHaveTextContent("X-Webhook-Signature");
    expect(sent).toContainEqual({
      method: "POST",
      path: `/v1/workspaces/${WS}/webhooks`,
      body: { url: "https://hooks.example.org/two" },
    });
    await user.click(
      within(hooks).getByRole("button", {
        name: "Remove webhook https://hooks.example.org/in",
      }),
    );
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "DELETE",
        path: `/v1/workspaces/${WS}/webhooks/${HOOK}`,
        body: undefined,
      });
    });
  });
});
