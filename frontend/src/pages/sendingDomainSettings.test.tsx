import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Settings › Sending domains (decision P6-D): the provider's records are
 * shown exactly, the screen says when no provider is connected, "Verify"
 * sends the version, an address is added with its streams, and members who
 * may not update the workspace only read.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const URL = `/w/${WS}/settings?section=sending`;
const stamp = "2026-11-01T09:30:00+00:00";
const DOMAIN = {
  id: "s1000000-0000-4000-8000-000000000001",
  domain: "acme-shop.nl",
  status: "pending",
  records: [
    {
      record: "DKIM",
      type: "TXT",
      name: "resend._domainkey",
      value: "p=MIGfMA0GCSq",
      ttl: "Auto",
      priority: null,
      status: "pending",
    },
  ],
  last_error: null,
  checked_at: stamp,
  created_at: stamp,
  claim_expires_at: "2026-11-08T09:30:00+00:00",
  version: 3,
  identities: [
    {
      id: "i1",
      address: "jan@acme-shop.nl",
      for_conversation: true,
      for_campaign: false,
      default_conversation: true,
      default_campaign: false,
      status: "active",
      usable: false,
      version: 1,
    },
  ],
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
    if (path === `${base}/sending-domains`) {
      return {
        status: 200,
        body: { items: [DOMAIN], provider_configured: false },
      };
    }
    return undefined;
  };
}

describe("settings › sending domains", () => {
  it("shows the provider's records exactly and the provider state", async () => {
    renderApp(URL, workspace(true));
    const section = await screen.findByRole("region", {
      name: "Sending domains",
    });
    expect(
      await within(section).findByText("acme-shop.nl"),
    ).toBeInTheDocument();
    expect(section).toHaveTextContent("resend._domainkey");
    expect(section).toHaveTextContent("p=MIGfMA0GCSq");
    expect(section).toHaveTextContent("jan@acme-shop.nl");
    expect(section).toHaveTextContent("Waiting for verification");
    expect(section).toHaveTextContent("No email provider is connected");
    expect(section).toHaveTextContent("the name is released");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("verifies with the version and adds an address with its streams", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      URL,
      workspace(true, (method, path) =>
        method === "POST"
          ? {
              status: path.endsWith("/verify") ? 200 : 201,
              body: path.endsWith("/identities")
                ? DOMAIN.identities[0]
                : DOMAIN,
            }
          : undefined,
      ),
    );
    const section = await screen.findByRole("region", {
      name: "Sending domains",
    });
    await user.click(
      await within(section).findByRole("button", { name: "Verify" }),
    );
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/verify"));
      expect(call?.headers["if-match"]).toBe('"3"');
    });
    await user.type(
      within(section).getByLabelText("Address before @acme-shop.nl"),
      "news",
    );
    // The two choices are one labelled group for screen readers.
    const uses = within(section).getByRole("group", {
      name: "Use this address for",
    });
    expect(within(uses).getAllByRole("checkbox")).toHaveLength(2);
    await user.click(
      within(section).getByRole("checkbox", { name: "Campaigns" }),
    );
    await user.click(
      within(section).getByRole("button", { name: "Add address" }),
    );
    await waitFor(() => {
      const post = sent.find((r) => r.path.endsWith("/identities"));
      expect(post?.body).toEqual({
        local_part: "news",
        for_conversation: true,
        for_campaign: true,
        default_conversation: true,
        default_campaign: true,
      });
    });
  });

  it("lets other members read only", async () => {
    renderApp(URL, workspace(false));
    const section = await screen.findByRole("region", {
      name: "Sending domains",
    });
    await within(section).findByText("acme-shop.nl");
    expect(within(section).queryByRole("button")).toBeNull();
    expect(within(section).queryByRole("textbox")).toBeNull();
  });
});
