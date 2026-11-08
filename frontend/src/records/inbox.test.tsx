import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * The inbox (decision P6-C): the list with unread state, opening a thread
 * marks it read, an email reply is sent with an Idempotency-Key and shown
 * as "Not sent yet" (never as sent) while queued, closing sends the
 * version, refusals say why, Read-only members get no composer, search
 * sends the words and says when nothing matches, and older threads load on
 * request (decision P6-C1).
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const CONV = "c1000000-0000-4000-8000-000000000001";
const CONTACT = "c0000000-0000-4000-8000-000000000001";
const OLDER = "c1000000-0000-4000-8000-000000000002";
const DEAL = "f0000000-0000-4000-8000-000000000001";
const stamp = "2026-11-01T09:30:00+00:00";
const REVIEW = {
  id: "r1000000-0000-4000-8000-000000000001",
  conversation_id: "c1000000-0000-4000-8000-000000000001",
  reason: "sender_mismatch",
  sender: "mallory@evil.test",
  subject: "Re: Your quote",
  body: "Please pay to this account.",
  truncated: false,
  attachments: [
    {
      filename: "invoice.pdf",
      content_type: "application/pdf",
      size: 2048,
      stored: false,
    },
  ],
  status: "pending",
  created_at: "2026-11-01T09:31:00+00:00",
  version: 1,
};

const SUMMARY = {
  id: CONV,
  contact_id: CONTACT,
  contact_name: "Ada Lovelace",
  channel: "email",
  subject: "Your quote",
  status: "open",
  assignee_user_id: null,
  last_message_at: stamp,
  unread: true,
  created_at: stamp,
  version: 3,
};

function thread(extra: Record<string, unknown> = {}) {
  return {
    ...SUMMARY,
    unread: false,
    contact_email: "ada@example.test",
    messages: [
      {
        id: "m1",
        kind: "inbound",
        body: "Can you send the quote?",
        author_user_id: ME,
        created_at: stamp,
        delivery: null,
      },
      {
        id: "m2",
        kind: "outbound",
        body: "Here it is.",
        author_user_id: ME,
        created_at: stamp,
        delivery: "queued",
      },
      {
        id: "m3",
        kind: "inbound",
        body: "Photo attached.",
        author_user_id: null,
        created_at: stamp,
        delivery: null,
        attachments: [
          {
            filename: "photo.jpg",
            content_type: "image/jpeg",
            size: 1024,
            stored: false,
          },
        ],
      },
    ],
    ...extra,
  };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  reply: boolean,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") {
      if (path === `${base}/conversations/${CONV}/read`) return { status: 204 };
      return onWrite?.(method, path, body);
    }
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [reply ? "Member" : "Read-only"],
          actions: {
            read_conversations: true,
            reply_conversations: reply,
            read_members: true,
          },
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: {
          items: [{ user_id: ME, status: "active", roles: ["Member"] }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      };
    }
    if (path.startsWith(`${base}/conversations?`)) {
      const query = new URLSearchParams(path.split("?")[1]);
      if (query.get("q") === "zebra")
        return { status: 200, body: { items: [], next_cursor: null } };
      if (query.get("cursor") === "next")
        return {
          status: 200,
          body: {
            items: [{ ...SUMMARY, id: OLDER, subject: "Older thread" }],
            next_cursor: null,
          },
        };
      return { status: 200, body: { items: [SUMMARY], next_cursor: "next" } };
    }
    if (path === `${base}/conversations/${CONV}`)
      return { status: 200, body: thread() };
    // The contact panel (P6-CX) reads the contact, its deals and appointments.
    if (path === `${base}/contacts/${CONTACT}`) {
      return {
        status: 200,
        body: {
          id: CONTACT,
          first_name: "Ada",
          last_name: "Lovelace",
          email: "ada@example.test",
          phone: "+44 20 7946 0000",
          job_title: "Engineer",
          city: "London",
          lifecycle_stage: "lead",
          source: "manual",
          company_id: null,
          company: null,
          owner_user_id: ME,
          created_at: stamp,
          updated_at: stamp,
          created_by_user_id: ME,
          updated_by_user_id: ME,
          version: 1,
          archived_at: null,
          tags: [{ id: "t1", name: "VIP" }],
          custom_fields: {},
        },
      };
    }
    if (path.startsWith(`${base}/opportunities?`)) {
      return {
        status: 200,
        body: {
          items: [
            {
              id: DEAL,
              title: "Analytical engine",
              amount: "900.00",
              currency: "EUR",
              weighted_amount: "180.00",
              pipeline_id: "p1",
              stage_id: "s1",
              stage: { id: "s1", name: "Qualified", probability: 20, position: 0 },
              stage_entered_at: stamp,
              owner_user_id: ME,
              expected_close_date: null,
              contact_id: CONTACT,
              contact: { id: CONTACT, name: "Ada Lovelace", archived: false },
              company_id: null,
              company: null,
              outcome: "open",
              lost_reason: null,
              closed_at: null,
              created_at: stamp,
              updated_at: stamp,
              created_by_user_id: ME,
              updated_by_user_id: ME,
              version: 1,
            },
          ],
          next_cursor: null,
          total: 1,
          total_capped: false,
        },
      };
    }
    if (path.startsWith(`${base}/appointments/upcoming`))
      return { status: 200, body: { items: [] } };
    if (path === `${base}/conversation-reviews`)
      return { status: 200, body: { items: reply ? [REVIEW] : [] } };
    return undefined;
  };
}

async function openThread(user: ReturnType<typeof userEvent.setup>) {
  const list = await screen.findByRole("region", { name: "Conversations" });
  await user.click(
    await within(list).findByRole("button", { name: /Ada Lovelace/ }),
  );
  return screen.findByRole("region", { name: "Conversation" });
}

describe("inbox", () => {
  it("shows the contact panel beside the thread, linking to the record and deals", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/inbox`, workspace(true));
    await openThread(user);
    const panel = await screen.findByRole("complementary", {
      name: "Contact details",
    });
    expect(await within(panel).findByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(panel).getByText("ada@example.test")).toBeInTheDocument();
    expect(within(panel).getByText("VIP")).toBeInTheDocument();
    const deal = await within(panel).findByRole("button", {
      name: /Analytical engine/,
    });
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(deal);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/opportunities`);
    });
    expect(router.state.location.search).toEqual({ record: DEAL });
  });

  it("hides and shows the contact panel from the thread header", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/inbox`, workspace(true));
    const pane = await openThread(user);
    const toggle = await within(pane).findByRole("button", {
      name: "Contact details",
    });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("complementary", { name: "Contact details" })).toBeNull();
    await user.click(toggle);
    const panel = await screen.findByRole("complementary", {
      name: "Contact details",
    });
    await user.click(
      await within(panel).findByRole("button", { name: /View full record/ }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/contacts`);
    });
    expect(router.state.location.search).toEqual({ record: CONTACT });
  });

  it("lists conversations with unread state and marks one read when opened", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/inbox`, workspace(true));
    const list = await screen.findByRole("region", { name: "Conversations" });
    const item = await within(list).findByRole("button", {
      name: /Ada Lovelace/,
    });
    expect(item).toHaveTextContent("Your quote");
    expect(item).toHaveTextContent("Unread");
    expect(await accessibilityViolations()).toEqual([]);
    const pane = await openThread(user);
    expect(
      await within(pane).findByText("Can you send the quote?"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        sent.some(
          (r) => r.method === "POST" && r.path.endsWith(`/${CONV}/read`),
        ),
      ).toBe(true);
    });
  });

  it("opens a new conversation from \"+ New\" (?create=conversation), only for a member who may", async () => {
    renderApp(`/w/${WS}/inbox?create=conversation`, workspace(true));
    expect(
      await screen.findByRole("dialog", { name: "New conversation" }),
    ).toBeInTheDocument();
  });

  it("ignores ?create=conversation for a Read-only member", async () => {
    renderApp(`/w/${WS}/inbox?create=conversation`, workspace(false));
    await screen.findByRole("region", { name: "Conversations" });
    expect(screen.queryByRole("dialog", { name: "New conversation" })).toBeNull();
  });

  it("opens the conversation named in the address, as from a contact's drawer", async () => {
    renderApp(`/w/${WS}/inbox?record=${CONV}`, workspace(true));
    expect(await screen.findByText("Can you send the quote?")).toBeInTheDocument();
  });

  it("shows a queued reply as not sent, never as sent", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/inbox`, workspace(true));
    const pane = await openThread(user);
    const messages = await within(pane).findByRole("list", {
      name: "Messages",
    });
    expect(messages).toHaveTextContent("Not sent yet");
    expect(messages).not.toHaveTextContent(/\bSent\b/);
  });

  it("queues an email reply with an idempotency key", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/inbox`,
      workspace(true, (method, path) =>
        method === "POST" && path.endsWith("/messages")
          ? { status: 201, body: thread() }
          : undefined,
      ),
    );
    const pane = await openThread(user);
    expect(
      within(pane).getByRole("button", { name: "Email reply" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(pane).getByText(/Nothing is sent while email sending is off/),
    ).toBeInTheDocument();
    await user.type(within(pane).getByLabelText("Email reply"), "Thanks!");
    await user.click(within(pane).getByRole("button", { name: "Queue reply" }));
    await waitFor(() => {
      const call = headersSent.find(
        (r) => r.method === "POST" && r.path.endsWith("/messages"),
      );
      expect(call?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    });
  });

  it("closes with the version and says why a refusal happened", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/inbox`,
      workspace(true, (method) =>
        method === "PATCH"
          ? { status: 409, body: { detail: { code: "stale_version" } } }
          : undefined,
      ),
    );
    const pane = await openThread(user);
    await user.click(within(pane).getByRole("button", { name: "Close" }));
    expect(await within(pane).findByRole("alert")).toHaveTextContent(
      "Someone else changed this conversation",
    );
    const call = headersSent.find((r) => r.method === "PATCH");
    expect(call?.headers["if-match"]).toBe('"3"');
  });

  it("offers Read-only members the thread without composer or controls", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/inbox`, workspace(false));
    const pane = await openThread(user);
    await within(pane).findByText("Can you send the quote?");
    expect(
      screen.queryByRole("button", { name: "New conversation" }),
    ).toBeNull();
    expect(within(pane).queryByRole("button", { name: "Close" })).toBeNull();
    expect(within(pane).queryByRole("textbox")).toBeNull();
  });

  it("searches across every status and says when nothing matches", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/inbox`, workspace(true));
    const list = await screen.findByRole("region", { name: "Conversations" });
    await within(list).findByRole("button", { name: /Ada Lovelace/ });
    await user.click(within(list).getByRole("button", { name: "All" }));
    await user.type(
      within(list).getByRole("searchbox", { name: "Search conversations" }),
      "zebra",
    );
    expect(
      await within(list).findByText("No conversations match"),
    ).toBeInTheDocument();
    const call = sent.find((r) => r.path.includes("q=zebra"));
    expect(call?.path).toContain("status=all");
  });

  it("loads older conversations on request", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/inbox`, workspace(true));
    const list = await screen.findByRole("region", { name: "Conversations" });
    await within(list).findByRole("button", { name: /Ada Lovelace/ });
    await user.click(within(list).getByRole("button", { name: "Load more" }));
    expect(
      await within(list).findByRole("button", { name: /Older thread/ }),
    ).toBeInTheDocument();
    expect(
      within(list).queryByRole("button", { name: "Load more" }),
    ).toBeNull();
  });

  it("lists received attachments as not stored", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/inbox`, workspace(true));
    const pane = await openThread(user);
    const messages = await within(pane).findByRole("list", {
      name: "Messages",
    });
    expect(messages).toHaveTextContent("photo.jpg");
    expect(messages).toHaveTextContent("Attachments (not stored)");
  });

  it("holds suspicious mail for review and decides it with the version", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/inbox`,
      workspace(true, (method, path) =>
        method === "POST" && path.endsWith("/accept")
          ? { status: 200, body: { ...REVIEW, status: "accepted", version: 2 } }
          : undefined,
      ),
    );
    const panel = await screen.findByRole("region", { name: "Needs review" });
    expect(panel).toHaveTextContent("Not sent by this conversation's contact");
    expect(panel).toHaveTextContent("From mallory@evil.test");
    expect(panel).toHaveTextContent("invoice.pdf");
    await user.click(
      within(panel).getByRole("button", { name: "Add to conversation" }),
    );
    await waitFor(() => {
      const call = headersSent.find((r) => r.path.endsWith("/accept"));
      expect(call?.headers["if-match"]).toBe('"1"');
    });
  });

  it("shows no review panel to Read-only members", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/inbox`, workspace(false));
    await openThread(user);
    expect(screen.queryByRole("region", { name: "Needs review" })).toBeNull();
    expect(sent.some((r) => r.path.includes("conversation-reviews"))).toBe(
      false,
    );
  });
});
