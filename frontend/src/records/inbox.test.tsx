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
const stamp = "2026-11-01T09:30:00+00:00";

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
});
