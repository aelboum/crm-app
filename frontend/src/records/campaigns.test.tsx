import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Campaigns (decision P7-C): the list says sending is unavailable and
 * never offers it; the estimate shows who may receive a campaign and why
 * others may not; steps send the version; only approvers see Approve and
 * Reject; Read-only members only read; editing an approved campaign warns
 * that the approval is withdrawn; refusals say why.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const ID = "ca000000-0000-4000-8000-000000000001";
const stamp = "2026-11-01T09:30:00+00:00";

function campaign(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    name: "Autumn news",
    subject: "News for {{first_name}}",
    body: "Hello {{first_name}},\nour autumn update.",
    segment: {
      stages: ["lead"],
      tag_ids: [],
      owner_ids: [],
      company_ids: [],
      all_contacts: false,
    },
    status: "awaiting_approval",
    estimate: { eligible: 12, excluded: { no_consent: 3, suppressed: 1 } },
    content_hash: "a".repeat(64),
    approved: false,
    approved_by_user_id: null,
    approved_at: null,
    submitted_by_user_id: ME,
    submitted_at: stamp,
    decision_note: null,
    created_by_user_id: ME,
    created_at: stamp,
    updated_at: stamp,
    version: 4,
    ...extra,
  };
}

const VIP = "70000000-0000-4000-8000-000000000001";

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  roles: { manage: boolean; approve: boolean },
  item: Record<string, unknown> = campaign(),
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [
            roles.approve ? "Admin" : roles.manage ? "Member" : "Read-only",
          ],
          actions: {
            read_campaigns: true,
            manage_campaigns: roles.manage,
            approve_campaigns: roles.approve,
          },
        },
      };
    }
    if (path === `${base}/campaigns`)
      return { status: 200, body: { items: [item], sending_available: false } };
    if (path === `${base}/tags`) {
      return {
        status: 200,
        body: {
          items: [{ id: VIP, name: "VIP", version: 1, created_at: stamp, updated_at: stamp }],
          max_tags: 500,
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: {
          items: [{ user_id: ME, status: "active", roles: ["Admin"], membership_id: "m1" }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      };
    }
    return undefined;
  };
}

async function openCampaign(user: ReturnType<typeof userEvent.setup>) {
  const list = await screen.findByRole("list", { name: "Campaigns" });
  await user.click(within(list).getByRole("button", { name: /Autumn news/ }));
  return screen.findByRole("region", { name: "Campaign" });
}

describe("campaigns", () => {
  it("lists campaigns, says sending is unavailable and never offers it", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: true }));
    expect(
      await screen.findByText(/Campaigns cannot be sent yet/),
    ).toBeInTheDocument();
    const pane = await openCampaign(user);
    expect(
      within(pane).queryByRole("button", { name: /Send|Queue/ }),
    ).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("shows who may receive it and why others may not", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: true, approve: false }),
    );
    const pane = await openCampaign(user);
    expect(pane).toHaveTextContent("12 contacts");
    expect(pane).toHaveTextContent("3 without marketing consent");
    expect(pane).toHaveTextContent("1 suppressed");
    expect(pane).toHaveTextContent("unsubscribe link");
  });

  it("lets an approver approve with the version", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: true, approve: true }, campaign(), (method, path) =>
        method === "POST" && path.endsWith("/approve")
          ? {
              status: 200,
              body: campaign({
                status: "approved",
                approved: true,
                version: 5,
              }),
            }
          : undefined,
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Approve" }));
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/approve"));
      expect(call?.headers["if-match"]).toBe('"4"');
    });
  });

  it("offers members no approval and says why a refusal happened", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "draft", estimate: null }),
        (method, path) =>
          method === "POST" && path.endsWith("/validate")
            ? {
                status: 422,
                body: {
                  detail: { code: "invalid_campaign", rule: "audience" },
                },
              }
            : undefined,
      ),
    );
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("button", { name: "Approve" })).toBeNull();
    await user.click(
      within(pane).getByRole("button", { name: "Check audience" }),
    );
    expect(await within(pane).findByRole("alert")).toHaveTextContent(
      "no contact may receive it",
    );
  });

  it("warns that editing an approved campaign withdraws its approval", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: true },
        campaign({ status: "approved", approved: true }),
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Edit" }));
    expect(
      await screen.findByText(/withdraws its approval/),
    ).toBeInTheDocument();
  });

  it("narrows the audience by tag and owner, and keeps company filters", async () => {
    const user = userEvent.setup();
    const COMPANY = "e0000000-0000-4000-8000-000000000001";
    let sentBody: unknown;
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({
          status: "draft",
          segment: { stages: ["lead"], tag_ids: [], owner_ids: [], company_ids: [COMPANY], all_contacts: false },
        }),
        (method, _path, body) => {
          if (method === "PATCH") {
            sentBody = body;
            return { status: 200, body: campaign() };
          }
          return undefined;
        },
      ),
    );
    const pane = await openCampaign(user);
    expect(within(pane).getByText(/Lead · 1 company/)).toBeInTheDocument();
    await user.click(within(pane).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit campaign" });
    expect(
      within(dialog).getByText(/must match every kind of filter/),
    ).toBeInTheDocument();
    await user.click(await within(dialog).findByRole("button", { name: "Tags" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "VIP" }));
    await user.keyboard("{Escape}");
    await user.click(within(dialog).getByRole("button", { name: "Owner" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "You" }));
    await user.keyboard("{Escape}");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(sentBody).toBeDefined();
    });
    expect((sentBody as { segment: unknown }).segment).toEqual({
      company_ids: [COMPANY],
      stages: ["lead"],
      tag_ids: [VIP],
      owner_ids: [ME],
      all_contacts: false,
    });
  });

  it("chooses the audience's companies: removes one and adds another (P7-CC)", async () => {
    const user = userEvent.setup();
    const ACME = "e0000000-0000-4000-8000-000000000001";
    const ZETA = "e0000000-0000-4000-8000-000000000002";
    const company = (id: string, name: string) => ({
      id,
      name,
      domain: null,
      website: null,
      phone: null,
      industry: null,
      city: null,
      country_code: null,
      archived: false,
      version: 1,
      created_at: stamp,
      updated_at: stamp,
    });
    let sentBody: unknown;
    const base = workspace(
      { manage: true, approve: false },
      campaign({
        status: "draft",
        segment: { stages: ["lead"], tag_ids: [], owner_ids: [], company_ids: [ACME], all_contacts: false },
      }),
      (method, _path, body) => {
        if (method === "PATCH") {
          sentBody = body;
          return { status: 200, body: campaign() };
        }
        return undefined;
      },
    );
    renderApp(`/w/${WS}/campaigns`, (method, path, body) => {
      if (method === "GET" && path === `/v1/workspaces/${WS}/companies/${ACME}`) {
        return { status: 200, body: company(ACME, "Acme BV") };
      }
      if (method === "GET" && path.startsWith(`/v1/workspaces/${WS}/companies?`)) {
        return {
          status: 200,
          body: { items: [company(ZETA, "Zeta Ltd")], next_cursor: null, total: 1, total_capped: false },
        };
      }
      return base(method, path, body);
    });
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit campaign" });
    const chosen = await within(dialog).findByRole("list", { name: "Chosen companies" });
    expect(await within(chosen).findByText("Acme BV")).toBeInTheDocument();
    await user.click(within(chosen).getByRole("button", { name: "Remove Acme BV" }));
    expect(within(dialog).queryByRole("list", { name: "Chosen companies" })).toBeNull();
    expect(within(dialog).getByText("Any company")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Add company" }));
    await user.click(await within(dialog).findByRole("option", { name: /Zeta Ltd/ }));
    expect(await within(dialog).findByRole("list", { name: "Chosen companies" })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(sentBody).toBeDefined();
    });
    expect((sentBody as { segment: { company_ids: string[] } }).segment.company_ids).toEqual([ZETA]);
  });

  it("lets Read-only members read only", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }),
    );
    const pane = await openCampaign(user);
    expect(screen.queryByRole("button", { name: "New campaign" })).toBeNull();
    expect(within(pane).queryByRole("button")).toBeNull();
  });
});
