import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Consent and suppression (decision P7-B): Settings › Suppression list (the
 * list, adding pasted addresses with a reason, refusals by line, removing
 * after a confirmation, what Members and Read-only members see) and the
 * contact drawer's Consent section (the email status, the history,
 * recording consent with its wording, withdrawing it). The server enforces
 * every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const SAM = "d0000000-0000-4000-8000-000000000001";
const stamp = "2026-10-28T09:30:00+00:00";

const MANAGER = {
  read_members: true,
  update_workspace: true,
  read_suppressions: true,
  manage_suppressions: true,
  create_contact: true,
  update_contact: true,
};
const MEMBER = { ...MANAGER, update_workspace: false, manage_suppressions: false };
const READER = { read_members: true, read_suppressions: false, manage_suppressions: false };

function row(id: string, email: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    email,
    reason: "manual",
    origin: "manual",
    note: null,
    created_by_user_id: ME,
    created_at: stamp,
    ...extra,
  };
}

const LIST = {
  items: [
    row("s1", "sam@example.test", { reason: "unsubscribed", origin: "consent_withdrawn" }),
    row("s2", "ada@example.test", { reason: "bounced", note: "Old newsletter tool." }),
  ],
  next_cursor: null,
  total: 2,
  total_capped: false,
};

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

const HISTORY = [
  {
    id: "r2",
    channel: "email",
    status: "withdrawn",
    method: "manual",
    wording: "Asked by phone.",
    form_id: null,
    form_name: null,
    recorded_by_user_id: ME,
    recorded_at: stamp,
  },
  {
    id: "r1",
    channel: "email",
    status: "granted",
    method: "web_form",
    wording: "Email me about offers.",
    form_id: "f1",
    form_name: "Contact us",
    recorded_by_user_id: null,
    recorded_at: stamp,
  },
];

const ALLOWED = { has_email: true, consent: "granted", suppression: null, marketing_allowed: true };
const NONE = { has_email: true, consent: "none", suppression: null, marketing_allowed: false };

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: {
    status?: unknown;
    history?: unknown[];
    onWrite?: (method: string, path: string, body: unknown) => Reply;
  } = {},
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return options.onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`${base}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (path.startsWith(`${base}/suppressions`)) return { status: 200, body: LIST };
    if (path.startsWith(`${base}/contacts?`)) {
      return { status: 200, body: { items: [sam], next_cursor: null, total: 1, total_capped: false } };
    }
    if (path === `${base}/contacts/${SAM}`) return { status: 200, body: sam };
    if (path === `${base}/contacts/${SAM}/email-status`) return { status: 200, body: options.status ?? NONE };
    if (path === `${base}/contacts/${SAM}/consent`) {
      return { status: 200, body: { items: options.history ?? HISTORY } };
    }
    return undefined;
  };
}

describe("suppression list", () => {
  it("lists the addresses with their reasons", async () => {
    renderApp(`/w/${WS}/settings?section=suppression`, workspace(MANAGER));
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("sam@example.test");
    expect(rows[1]).toHaveTextContent("Unsubscribed · Consent withdrawn");
    expect(rows[2]).toHaveTextContent("Bounced");
    expect(rows[2]).toHaveTextContent("Old newsletter tool.");
    expect(screen.getByText("2 addresses")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("adds pasted addresses with a reason", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/settings?section=suppression`,
      workspace(MANAGER, { onWrite: () => ({ status: 201, body: { added: 2, already_suppressed: 1 } }) }),
    );
    await user.type(
      await screen.findByLabelText("Email addresses"),
      "new@example.test, other@example.test{enter}sam@example.test",
    );
    await user.selectOptions(screen.getByLabelText("Reason"), "bounced");
    await user.click(screen.getByRole("button", { name: "Suppress" }));
    expect(await screen.findByText("2 addresses suppressed · 1 was already on the list.")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({
      emails: ["new@example.test", "other@example.test", "sam@example.test"],
      reason: "bounced",
      note: null,
    });
  });

  it("names refused lines, never the addresses", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/settings?section=suppression`,
      workspace(MANAGER, {
        onWrite: () => ({ status: 422, body: { detail: { code: "invalid_emails", positions: [1] } } }),
      }),
    );
    await user.type(await screen.findByLabelText("Email addresses"), "ok@example.test{enter}nonsense");
    await user.click(screen.getByRole("button", { name: "Suppress" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Line 2 is not an email address.");
  });

  it("removes an address after a confirmation", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/settings?section=suppression`,
      workspace(MANAGER, { onWrite: () => ({ status: 204 }) }),
    );
    await user.click(await screen.findByRole("button", { name: "Remove ada@example.test" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Remove from the suppression list?" });
    expect(dialog).toHaveTextContent("ada@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "DELETE")?.path).toBe(`/v1/workspaces/${WS}/suppressions/s2`);
    });
  });

  it("shows Members the list without changes", async () => {
    renderApp(`/w/${WS}/settings?section=suppression`, workspace(MEMBER));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.queryByLabelText("Email addresses")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(screen.getByText("Only Owners and Admins add or remove addresses.")).toBeInTheDocument();
  });

  it("does not load the list for a Read-only member", async () => {
    const { sent } = renderApp(`/w/${WS}/settings?section=suppression`, workspace(READER));
    expect(await screen.findByText("You do not have access to the suppression list.")).toBeInTheDocument();
    expect(sent.some((r) => r.path.includes("/suppressions"))).toBe(false);
  });
});

async function consentSection() {
  return screen.findByRole("region", { name: "Consent" });
}

describe("a contact's consent", () => {
  it("shows the status and every record", async () => {
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace(MANAGER, { status: ALLOWED }));
    const section = await consentSection();
    expect(await within(section).findByText("May receive marketing email")).toBeInTheDocument();
    const items = within(section).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Email consent withdrawn");
    expect(items[0]).toHaveTextContent("Recorded by You");
    expect(items[0]).toHaveTextContent("Asked by phone.");
    expect(items[1]).toHaveTextContent("Through the form Contact us");
    expect(within(section).getByText(/not been confirmed/)).toBeInTheDocument();
  });

  it("says when the address is suppressed", async () => {
    const status = {
      has_email: true,
      consent: "withdrawn",
      suppression: { id: "s1", reason: "unsubscribed", created_at: stamp },
      marketing_allowed: false,
    };
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace(MANAGER, { status }));
    const section = await consentSection();
    expect(await within(section).findByText(/Suppressed: Unsubscribed/)).toBeInTheDocument();
    // Already withdrawn and suppressed: nothing left to withdraw.
    expect(within(section).queryByRole("button", { name: "Withdraw consent" })).toBeNull();
  });

  it("records consent with the exact wording", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(MANAGER, { onWrite: () => ({ status: 200, body: ALLOWED }) }),
    );
    const section = await consentSection();
    await user.click(await within(section).findByRole("button", { name: "Record consent" }));
    const dialog = await screen.findByRole("dialog", { name: "Record email consent" });
    expect(await accessibilityViolations()).toEqual([]);
    await user.type(within(dialog).getByLabelText("Wording agreed to"), " Yes, email me about offers. ");
    await user.click(within(dialog).getByRole("button", { name: "Record consent" }));
    expect(await screen.findByText("Consent recorded.")).toBeInTheDocument();
    const post = sent.find((r) => r.method === "POST");
    expect(post?.path).toBe(`/v1/workspaces/${WS}/contacts/${SAM}/consent`);
    expect(post?.body).toEqual({ wording: "Yes, email me about offers." });
  });

  it("withdraws consent, which suppresses the address", async () => {
    const user = userEvent.setup();
    const suppressed = {
      has_email: true,
      consent: "withdrawn",
      suppression: { id: "s9", reason: "unsubscribed", created_at: stamp },
      marketing_allowed: false,
    };
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(MANAGER, { status: ALLOWED, onWrite: () => ({ status: 200, body: suppressed }) }),
    );
    const section = await consentSection();
    await user.click(await within(section).findByRole("button", { name: "Withdraw consent" }));
    const dialog = await screen.findByRole("dialog", { name: "Withdraw email consent" });
    expect(dialog).toHaveTextContent(/added to the suppression list/);
    await user.click(within(dialog).getByRole("button", { name: "Withdraw consent" }));
    expect(await screen.findByText("Consent withdrawn and address suppressed.")).toBeInTheDocument();
    const post = sent.find((r) => r.method === "POST");
    expect(post?.path).toBe(`/v1/workspaces/${WS}/contacts/${SAM}/consent/withdraw`);
    expect(post?.body).toEqual({ note: null });
  });

  it("offers no changes to members who cannot update the contact", async () => {
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace({ ...MANAGER, update_contact: false }));
    const section = await consentSection();
    await within(section).findByText("No consent: no marketing email.");
    expect(within(section).queryByRole("button", { name: "Record consent" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "Withdraw consent" })).toBeNull();
  });
});
