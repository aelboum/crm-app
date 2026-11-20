import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { fileDownload } from "../api/exportContacts";
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
 * that the approval is withdrawn; refusals say why. In a rehearsal
 * workspace (decision P7-R) an approver may queue an approved campaign,
 * labelled as a rehearsal.
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
  rehearsal = false,
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
            export_records: roles.approve,
          },
        },
      };
    }
    if (path.startsWith(`${base}/campaigns?`)) {
      const query = new URLSearchParams(path.split("?")[1]);
      const name = String(item.name).toLowerCase();
      const shown =
        query.get("archived") !== "true" &&
        (query.get("status") ?? item.status) === item.status &&
        name.includes((query.get("search") ?? "").toLowerCase());
      const items = shown ? [item] : [];
      return {
        status: 200,
        body: {
          items,
          next_cursor: null,
          total: items.length,
          total_capped: false,
          sending_available: false,
          rehearsal,
        },
      };
    }
    if (path === `${base}/campaigns/${ID}/report`) {
      return {
        status: 200,
        body: {
          campaign_id: ID,
          status: item.status,
          recipients: 12,
          outcomes: {
            waiting: 0,
            sent: 3,
            delivered: 7,
            bounced: 1,
            complained: 0,
            suppressed: 1,
            not_sent: 0,
            unknown: 0,
            rehearsed: 0,
          },
          unsubscribed: 2,
        },
      };
    }
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

  it("queues an approved campaign as a rehearsal where that is allowed", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: true },
        campaign({ status: "approved", approved: true }),
        (method, path) =>
          method === "POST" && path.endsWith("/queue")
            ? { status: 200, body: campaign({ status: "queued", version: 5 }) }
            : undefined,
        true,
      ),
    );
    expect(
      await screen.findByText(/Rehearsal workspace: .* no email is sent/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Campaigns cannot be sent yet/)).toBeNull();
    const pane = await openCampaign(user);
    await user.click(
      within(pane).getByRole("button", { name: "Queue as a rehearsal" }),
    );
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/queue"));
      expect(call?.headers["if-match"]).toBe('"4"');
    });
  });

  it("shows a started campaign's results and says sent is not delivered (P7-RP)", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: false, approve: false },
        campaign({ status: "completed" }),
      ),
    );
    const pane = await openCampaign(user);
    const results = await within(pane).findByRole("region", {
      name: "Results",
    });
    await within(results).findByText("Recipients");
    const row = (label: string) =>
      within(results).getByText(label).parentElement?.textContent;
    expect(row("Recipients")).toBe("Recipients12");
    expect(row("Accepted by the provider")).toBe("Accepted by the provider3");
    expect(row("Delivered")).toBe("Delivered7");
    expect(row("Unsubscribed")).toBe("Unsubscribed2");
    // Outcomes with no email are left out.
    expect(within(results).queryByText("Marked as spam")).toBeNull();
    expect(
      within(results).getByText(/does not mean delivered/),
    ).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("archives a finished campaign with the version (P7-AR)", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "completed" }),
        (method, path) =>
          method === "POST" && path.endsWith("/archive")
            ? {
                status: 200,
                body: campaign({ status: "completed", archived_at: stamp, version: 5 }),
              }
            : undefined,
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Archive" }));
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/archive"));
      expect(call?.headers["if-match"]).toBe('"4"');
    });
  });

  it("deletes a campaign never queued after a confirmation (P7-DL)", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "draft" }),
        (method) => (method === "DELETE" ? { status: 204 } : undefined),
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Delete campaign?" });
    expect(dialog).toHaveTextContent(/Autumn news is deleted for good/);
    expect(headersSent.filter((r) => r.method === "DELETE")).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      const call = headersSent.find((r) => r.method === "DELETE");
      expect(call?.path).toBe(`/v1/workspaces/${WS}/campaigns/${ID}`);
      expect(call?.headers["if-match"]).toBe('"4"');
    });
  });

  it("offers no deletion once a campaign awaits approval or was queued", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: true }));
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("offers no archiving before a campaign is finished, nor to Read-only members", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: true }));
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("button", { name: "Archive" })).toBeNull();
  });

  it("lists archived campaigns on request and says what archiving keeps", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }, campaign({ status: "cancelled" })),
    );
    await openCampaign(user);
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    const toggle = screen.getByRole("button", { name: "Show archived" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(await screen.findByText("No archived campaigns")).toBeInTheDocument();
    expect(screen.getByText(/results and history are kept/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show current" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("sums up a started campaign's results in the list", async () => {
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }, campaign({ status: "completed" })),
    );
    const list = await screen.findByRole("list", { name: "Campaigns" });
    expect(
      await within(list).findByText(
        "12 recipients · Accepted by the provider 3 · Delivered 7 · Bounced 1 · Not sent: suppressed 1",
      ),
    ).toBeInTheDocument();
  });

  it("shows no list summary before a campaign is queued", async () => {
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: true }));
    const list = await screen.findByRole("list", { name: "Campaigns" });
    await within(list).findByText("Autumn news");
    expect(within(list).queryByText(/recipient/)).toBeNull();
  });

  it("searches by name and filters by status, and says when nothing matches (P7-CL)", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }),
    );
    const list = await screen.findByRole("list", { name: "Campaigns" });
    expect(within(list).getByText("Autumn news")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search campaigns" }), "autumn");
    expect(await screen.findByText("1 campaign")).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "Draft");
    expect(await screen.findByText("No campaigns match")).toBeInTheDocument();
    const last = sent.filter((r) => r.path.includes("/campaigns?")).at(-1);
    expect(last?.path).toContain("status=draft");
    expect(last?.path).toContain("search=autumn");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("loads the next page of campaigns from the cursor", async () => {
    const user = userEvent.setup();
    const second = campaign({ id: "ca000000-0000-4000-8000-000000000002", name: "Winter news" });
    const base = workspace({ manage: false, approve: false });
    const { sent } = renderApp(`/w/${WS}/campaigns`, (method, path, body) => {
      if (method === "GET" && path.startsWith(`/v1/workspaces/${WS}/campaigns?`)) {
        const next = path.includes("cursor=c2");
        return {
          status: 200,
          body: {
            items: [next ? second : campaign()],
            next_cursor: next ? null : "c2",
            total: 2,
            total_capped: false,
            sending_available: false,
            rehearsal: false,
          },
        };
      }
      return base(method, path, body);
    });
    const list = await screen.findByRole("list", { name: "Campaigns" });
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await within(list).findByText("Winter news")).toBeInTheDocument();
    expect(within(list).getByText("Autumn news")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    expect(sent.some((r) => r.path.includes("cursor=c2"))).toBe(true);
  });

  it("sorts by name or last update, newest first by default (P7-SO)", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }),
    );
    await screen.findByRole("list", { name: "Campaigns" });
    const lists = () => sent.filter((r) => r.path.includes("/campaigns?"));
    expect(lists().at(-1)?.path).not.toContain("order=");
    const sort = screen.getByRole("combobox", { name: "Sort" });
    expect(sort).toHaveValue("created_at");
    await user.selectOptions(sort, "Name A to Z");
    await waitFor(() => {
      expect(lists().at(-1)?.path).toContain("order=name");
    });
    await user.selectOptions(sort, "Last updated");
    await waitFor(() => {
      expect(lists().at(-1)?.path).toContain("order=updated_at");
    });
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("duplicates a campaign into a new draft (P7-DU)", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "completed" }),
        (method, path) =>
          method === "POST" && path.endsWith("/duplicate")
            ? {
                status: 201,
                body: campaign({
                  id: "ca000000-0000-4000-8000-000000000009",
                  name: "Autumn news (copy)",
                  status: "draft",
                  estimate: null,
                  version: 1,
                }),
              }
            : undefined,
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Duplicate" }));
    await waitFor(() => {
      const call = sent.find((r) => r.path.endsWith(`/campaigns/${ID}/duplicate`));
      expect(call?.method).toBe("POST");
      expect(call?.body).toEqual({});
    });
  });

  it("offers Read-only members no duplicate", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: false, approve: false }));
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("button", { name: "Duplicate" })).toBeNull();
  });

  it("downloads a campaign's results as CSV for those who may export (P7-RX)", async () => {
    const user = userEvent.setup();
    const save = vi
      .spyOn(fileDownload, "save")
      .mockImplementation(() => undefined);
    const base = workspace({ manage: true, approve: true }, campaign({ status: "completed" }));
    const { sent } = renderApp(`/w/${WS}/campaigns`, (method, path, body) =>
      path.endsWith(`/campaigns/${ID}/results.csv`)
        ? { status: 200, body: "email,contact_id,outcome,added_at,unsubscribed_at" }
        : base(method, path, body),
    );
    const pane = await openCampaign(user);
    const results = await within(pane).findByRole("region", { name: "Results" });
    await user.click(await within(results).findByRole("button", { name: "Download CSV" }));
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
    expect(save.mock.calls[0]?.[1]).toBe("campaign-results.csv");
    expect(sent.some((r) => r.path.endsWith("/results.csv"))).toBe(true);
    expect(await accessibilityViolations()).toEqual([]);
    save.mockRestore();
  });

  it("says when the results download is refused for too many tries", async () => {
    const user = userEvent.setup();
    const base = workspace({ manage: true, approve: true }, campaign({ status: "completed" }));
    renderApp(`/w/${WS}/campaigns`, (method, path, body) =>
      path.endsWith("/results.csv")
        ? { status: 429, body: { detail: { code: "rate_limited" } } }
        : base(method, path, body),
    );
    const pane = await openCampaign(user);
    const results = await within(pane).findByRole("region", { name: "Results" });
    await user.click(await within(results).findByRole("button", { name: "Download CSV" }));
    expect(await within(results).findByRole("alert")).toHaveTextContent(
      "Too many downloads for now",
    );
  });

  it("offers no results download to Members", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: true, approve: false }, campaign({ status: "completed" })),
    );
    const pane = await openCampaign(user);
    const results = await within(pane).findByRole("region", { name: "Results" });
    await within(results).findByText("Recipients");
    expect(within(results).queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("previews the campaign for a chosen contact and says if they may receive it (P7-PV)", async () => {
    const user = userEvent.setup();
    const SAM = "c0000000-0000-4000-8000-000000000005";
    const sam = {
      id: SAM,
      first_name: "Sam",
      last_name: "Jansen",
      email: "sam@example.test",
      phone: null,
      job_title: null,
      city: null,
      lifecycle_stage: "lead",
      source: "manual",
      company_id: null,
      company: null,
      owner_user_id: null,
      created_at: stamp,
      updated_at: stamp,
      created_by_user_id: ME,
      updated_by_user_id: ME,
      version: 1,
      archived_at: null,
      tags: [],
      custom_fields: {},
    };
    const base = workspace({ manage: false, approve: false });
    const { sent } = renderApp(`/w/${WS}/campaigns`, (method, path, body) => {
      if (path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
        return {
          status: 200,
          body: { items: [sam], next_cursor: null, total: 1, total_capped: false },
        };
      }
      if (path.startsWith(`/v1/workspaces/${WS}/campaigns/${ID}/preview?`)) {
        return {
          status: 200,
          body: {
            campaign_id: ID,
            contact_id: SAM,
            subject: "News for Sam",
            body: "Hello Sam,\nour autumn update.\n\n--\nYou receive this email from Acme.\nUnsubscribe: [unsubscribe link]",
            audience: "excluded",
            reason: "no_consent",
          },
        };
      }
      return base(method, path, body);
    });
    const pane = await openCampaign(user);
    const region = within(pane).getByRole("region", { name: "Preview" });
    // The campaign's own email is a group with another name: one "Preview" only.
    expect(within(pane).getByRole("group", { name: "Campaign email" })).toBeInTheDocument();
    expect(within(pane).getAllByLabelText("Preview")).toHaveLength(1);
    await user.click(within(region).getByRole("button", { name: "Choose a contact" }));
    await user.click(await within(region).findByRole("option", { name: /Sam Jansen/ }));
    expect(await within(region).findByText("News for Sam")).toBeInTheDocument();
    expect(
      within(region).getByText("In the audience, but will not receive it: no marketing consent."),
    ).toBeInTheDocument();
    expect(sent.some((r) => r.path.includes(`/preview?contact_id=${SAM}`))).toBe(true);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("schedules an approved campaign with the version and a time (P7-SC)", async () => {
    const user = userEvent.setup();
    const { headersSent, sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: true },
        campaign({ status: "approved", approved: true }),
        (method, path) =>
          method === "POST" && path.endsWith("/schedule")
            ? {
                status: 200,
                body: campaign({
                  status: "approved",
                  approved: true,
                  scheduled_at: "2026-12-01T09:00:00+00:00",
                  version: 5,
                }),
              }
            : undefined,
        true,
      ),
    );
    const pane = await openCampaign(user);
    await user.click(within(pane).getByRole("button", { name: "Schedule" }));
    const input = within(pane).getByLabelText("Queue at");
    await user.type(input, "2026-12-01T10:00");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(pane).getByRole("button", { name: "Save schedule" }));
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/schedule"));
      expect(call?.headers["if-match"]).toBe('"4"');
    });
    const body = sent.find((r) => r.path.endsWith("/schedule"))?.body as { at: string };
    expect(body.at).toBe(new Date("2026-12-01T10:00").toISOString());
  });

  it("shows when a campaign is scheduled and unschedules it", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: true },
        campaign({
          status: "approved",
          approved: true,
          scheduled_at: "2026-12-01T09:00:00+00:00",
        }),
        (method, path) =>
          method === "POST" && path.endsWith("/unschedule")
            ? { status: 200, body: campaign({ status: "approved", approved: true, version: 5 }) }
            : undefined,
        true,
      ),
    );
    const pane = await openCampaign(user);
    expect(within(pane).getByText("Scheduled for")).toBeInTheDocument();
    expect(within(pane).queryByRole("button", { name: "Schedule" })).toBeNull();
    await user.click(within(pane).getByRole("button", { name: "Unschedule" }));
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/unschedule"));
      expect(call?.headers["if-match"]).toBe('"4"');
    });
  });

  it("offers Members no scheduling", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "approved", approved: true }),
        undefined,
        true,
      ),
    );
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("button", { name: "Schedule" })).toBeNull();
  });

  it("says when a tag in the audience was deleted (P7-ST)", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({ status: "draft", missing_tag_ids: [VIP] }),
      ),
    );
    const pane = await openCampaign(user);
    expect(
      within(pane).getByText(/A tag in this audience was deleted\. Edit the audience/),
    ).toBeInTheDocument();
  });

  it("removes deleted tags only after a confirmation (P7-ST follow-up)", async () => {
    const user = userEvent.setup();
    const stale = campaign({
      status: "draft",
      segment: {
        stages: ["lead"],
        tag_ids: [VIP],
        owner_ids: [],
        company_ids: [],
        all_contacts: false,
      },
      missing_tag_ids: [VIP],
    });
    const { sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: true, approve: false }, stale, () => ({
        status: 200,
        body: { ...stale, missing_tag_ids: [], version: 5 },
      })),
    );
    const pane = await openCampaign(user);
    await user.click(
      within(pane).getByRole("button", { name: "Remove the deleted tag" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Remove deleted tags?",
    });
    expect(dialog).toHaveTextContent(/may include more contacts/);
    expect(sent.filter((r) => r.method === "POST")).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST").map((r) => r.path)).toEqual([
        `/v1/workspaces/${WS}/campaigns/${ID}/remove-deleted-tags`,
      ]);
    });
  });

  it("offers no removal when only deleted tags choose the audience", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace(
        { manage: true, approve: false },
        campaign({
          status: "draft",
          segment: {
            stages: [],
            tag_ids: [VIP],
            owner_ids: [],
            company_ids: [],
            all_contacts: false,
          },
          missing_tag_ids: [VIP],
        }),
      ),
    );
    const pane = await openCampaign(user);
    expect(within(pane).getByText(/A tag in this audience was deleted/)).toBeInTheDocument();
    expect(
      within(pane).queryByRole("button", { name: /Remove the deleted/ }),
    ).toBeNull();
  });

  it("shows no results before a campaign is queued", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: true }));
    const pane = await openCampaign(user);
    expect(within(pane).queryByRole("region", { name: "Results" })).toBeNull();
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

  it("lists the automations this campaign starts and opens a new one for it (P8-C)", async () => {
    const user = userEvent.setup();
    const OTHER = "ca000000-0000-4000-8000-000000000002";
    const started = (
      id: string,
      name: string,
      type: string,
      campaignId: string | null,
    ) => ({
      id,
      name,
      status: "active",
      trigger_type: type,
      definition: {
        trigger: { type, campaign_id: campaignId },
        condition: null,
        yes: [{ type: "add_tag", tag_id: VIP }],
        no: [],
      },
      active_version: 1,
      created_at: stamp,
      updated_at: stamp,
      version: 1,
    });
    const items = [
      started("a1000000-0000-4000-8000-000000000001", "After the news", "campaign_sent", ID),
      started("a1000000-0000-4000-8000-000000000002", "Any unsubscribe", "campaign_unsubscribed", null),
      started("a1000000-0000-4000-8000-000000000003", "Spring only", "campaign_sent", OTHER),
    ];
    const inner = workspace({ manage: true, approve: false });
    const base = `/v1/workspaces/${WS}`;
    renderApp(`/w/${WS}/campaigns`, (method, path, body) => {
      if (method === "GET" && path === `${base}/access`) {
        return {
          status: 200,
          body: {
            membership_id: "m1",
            roles: ["Member"],
            actions: {
              read_campaigns: true,
              manage_campaigns: true,
              read_automations: true,
              manage_automations: true,
            },
          },
        };
      }
      if (method === "GET" && path === `${base}/automations`)
        return { status: 200, body: { items } };
      return inner(method, path, body);
    });
    const pane = await openCampaign(user);
    const group = await within(pane).findByRole("group", {
      name: "Automations started by this campaign",
    });
    expect(await within(group).findByText("After the news")).toBeInTheDocument();
    expect(within(group).getByText("on sending")).toBeInTheDocument();
    expect(within(group).getByText("Any unsubscribe")).toBeInTheDocument();
    expect(
      within(group).getByText("on unsubscribing (any campaign)"),
    ).toBeInTheDocument();
    expect(within(group).queryByText("Spring only")).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);

    await user.click(
      within(group).getByRole("button", {
        name: "New automation for this campaign",
      }),
    );
    const editor = await screen.findByRole("dialog");
    expect(within(editor).getByLabelText("When this happens")).toHaveValue(
      "campaign_sent",
    );
    expect(within(editor).getByLabelText("Campaign")).toHaveValue(ID);
  });

  it("hides the campaign's automations from members who may not read them", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace({ manage: true, approve: false }));
    await openCampaign(user);
    expect(
      screen.queryByRole("group", {
        name: "Automations started by this campaign",
      }),
    ).toBeNull();
  });

  it("lets Read-only members read only", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/campaigns`,
      workspace({ manage: false, approve: false }),
    );
    const pane = await openCampaign(user);
    expect(screen.queryByRole("button", { name: "New campaign" })).toBeNull();
    // Only the preview's contact chooser, which reads (P7-PV); no step.
    expect(within(pane).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Choose a contact",
    ]);
  });
});
