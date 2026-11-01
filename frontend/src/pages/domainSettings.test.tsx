import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Settings › Domains (decision P12-D): a claim shows the exact TXT record
 * to publish, "Check now" sends the version, a check that cannot look DNS
 * up says so, adding sends the hostname, and members who may not update
 * the workspace only read.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const URL = `/w/${WS}/settings?section=domains`;
const stamp = "2026-11-01T09:30:00+00:00";
const DOMAIN = {
  id: "d1000000-0000-4000-8000-000000000001",
  hostname: "forms.acme-shop.nl",
  status: "pending",
  record_name: "_leadstack-challenge.forms.acme-shop.nl",
  record_value: "leadstack-verification=0123456789abcdef0123456789abcdef", // pragma: allowlist secret
  expires_at: "2026-11-08T09:30:00+00:00",
  verified_at: null,
  checked_at: stamp,
  last_error: "resolver_unavailable",
  created_at: stamp,
  version: 2,
};

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  canEdit: boolean,
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
          roles: [canEdit ? "Owner" : "Member"],
          actions: { update_workspace: canEdit, read_members: true },
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: { items: [], total: 0, limit: 50, offset: 0 },
      };
    }
    if (path === `${base}/domains`)
      return { status: 200, body: { items: [DOMAIN] } };
    return undefined;
  };
}

describe("settings › domains", () => {
  it("shows the record to publish and why it is not verified yet", async () => {
    renderApp(URL, workspace(true));
    const section = await screen.findByRole("region", { name: "Domains" });
    expect(
      await within(section).findByText("forms.acme-shop.nl"),
    ).toBeInTheDocument();
    expect(section).toHaveTextContent(
      "_leadstack-challenge.forms.acme-shop.nl",
    );
    expect(section).toHaveTextContent("leadstack-verification=0123456789"); // pragma: allowlist secret
    expect(section).toHaveTextContent("DNS checks are not set up");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("checks with the version and adds a domain", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      URL,
      workspace(true, (method, path) =>
        method === "POST"
          ? { status: path.endsWith("/check") ? 200 : 201, body: DOMAIN }
          : undefined,
      ),
    );
    const section = await screen.findByRole("region", { name: "Domains" });
    await user.click(
      await within(section).findByRole("button", { name: "Check now" }),
    );
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/check"));
      expect(call?.headers["if-match"]).toBe('"2"');
    });
    await user.type(
      within(section).getByLabelText("Domain name"),
      "book.acme-shop.nl",
    );
    await user.click(
      within(section).getByRole("button", { name: "Add domain" }),
    );
    await waitFor(() => {
      const post = sent.find(
        (r) => r.method === "POST" && r.path.endsWith("/domains"),
      );
      expect(post?.body).toEqual({ hostname: "book.acme-shop.nl" });
    });
  });

  it("lets other members read only", async () => {
    renderApp(URL, workspace(false));
    const section = await screen.findByRole("region", { name: "Domains" });
    await within(section).findByText("forms.acme-shop.nl");
    expect(within(section).queryByRole("button")).toBeNull();
    expect(within(section).queryByLabelText("Domain name")).toBeNull();
  });
});
