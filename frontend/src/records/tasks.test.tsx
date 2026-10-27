import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Tasks (decision P4-C): the tabs with their counts, the groups by the
 * viewer's own day, quick add (sending a real due time and an idempotency
 * key), completing with the task's version, deleting after confirming, and
 * what a Read-only member is offered. The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const stamp = "2026-10-27T09:30:00+00:00";
const T1 = "a1000000-0000-4000-8000-000000000001";
const T2 = "a1000000-0000-4000-8000-000000000002";
const T3 = "a1000000-0000-4000-8000-000000000003";

function task(id: string, title: string, due: Date | null, extra: Record<string, unknown> = {}) {
  return {
    id,
    title,
    priority: "medium",
    due_at: due ? due.toISOString() : null,
    assignee_user_id: "u-me",
    contact_id: null,
    contact: null,
    company_id: null,
    company: null,
    opportunity_id: null,
    opportunity: null,
    done: false,
    completed_at: null,
    completed_by_user_id: null,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: "u-me",
    updated_by_user_id: "u-me",
    version: 2,
    ...extra,
  };
}

const later = (hours: number) => new Date(Date.now() + hours * 3_600_000);
const ITEMS = [
  task(T1, "Call back Sam", later(-26), {
    priority: "high",
    contact_id: "c1",
    contact: { id: "c1", name: "Sam Jansen", archived: false },
  }),
  task(T2, "Send the proposal", null),
  task(T3, "Plan the demo", later(24 * 8)),
];
const DONE = [task(T2, "Old task", null, { done: true, completed_at: stamp, completed_by_user_id: "u-me" })];

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === base) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`${base}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (method === "GET" && path.startsWith(`${base}/tasks/counts`)) {
      return { status: 200, body: { open: 3, mine: 3, overdue: 1, done: 4 } };
    }
    if (method === "GET" && path.startsWith(`${base}/tasks?`)) {
      const items = path.includes("status=done") ? DONE : ITEMS;
      return { status: 200, body: { items, next_cursor: null, total: items.length, total_capped: false } };
    }
    if (method !== "GET" && path.startsWith(`${base}/tasks`)) return onWrite?.(method, path, body);
    return undefined;
  };
}

const MEMBER = { read_members: true, create_task: true, update_task: true, delete_task: true };
const READER = { read_members: true, create_task: false, update_task: false, delete_task: false };
const URL = `/w/${WS}/tasks`;

describe("tasks page", () => {
  it("shows the tabs with counts and the open tasks grouped by due time", async () => {
    renderApp(URL, workspace(MEMBER));
    const overdue = await screen.findByRole("region", { name: /Overdue/ });
    expect(within(overdue).getByText("Call back Sam")).toBeInTheDocument();
    expect(within(overdue).getByRole("button", { name: "Sam Jansen" })).toBeInTheDocument();
    expect(within(overdue).getByText("High")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /Upcoming/ })).getByText("Plan the demo")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: /No due date/ })).getByText("Send the proposal"),
    ).toBeInTheDocument();
    const tabs = screen.getByRole("group", { name: "Task views" });
    expect(within(tabs).getByRole("button", { name: /Overdue/ })).toHaveTextContent("1");
    expect(within(tabs).getByRole("button", { name: /Completed/ })).toHaveTextContent("4");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("asks the server for overdue and completed tasks", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace(MEMBER));
    const tabs = await screen.findByRole("group", { name: "Task views" });
    await user.click(within(tabs).getByRole("button", { name: /Overdue/ }));
    await waitFor(() => {
      expect(sent.some((r) => r.path.includes("/tasks?") && r.path.includes("overdue=true"))).toBe(true);
    });
    await user.click(within(tabs).getByRole("button", { name: /Completed/ }));
    expect(await screen.findByText("Old task")).toBeInTheDocument();
    const done = sent.find((r) => r.path.includes("status=done"));
    expect(new URLSearchParams(done?.path.split("?")[1]).get("sort")).toBe("completed_at");
  });

  it("adds a task with a real due time and an idempotency key", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      URL,
      workspace(MEMBER, (method) => (method === "POST" ? { status: 201, body: ITEMS[1] } : undefined)),
    );
    await user.type(await screen.findByLabelText("New task"), "Email the quote");
    await user.selectOptions(screen.getByLabelText("Due"), "tomorrow");
    await user.selectOptions(screen.getByLabelText("Priority"), "high");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    const post = sent.find((r) => r.method === "POST");
    expect(post?.body).toMatchObject({ title: "Email the quote", priority: "high", assignee_user_id: "u-me" });
    const due = new Date((post?.body as { due_at: string }).due_at);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    expect([due.getHours(), due.getMinutes(), due.getDate()]).toEqual([17, 0, tomorrow.getDate()]);
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("completes a task with its version and deletes one after confirming", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      URL,
      workspace(MEMBER, (method) => (method === "DELETE" ? { status: 204 } : { status: 200, body: ITEMS[0] })),
    );
    await user.click(await screen.findByRole("checkbox", { name: "Complete Call back Sam" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ done: true });
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"2"');
    await user.click(screen.getByRole("button", { name: "Delete Plan the demo" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Delete this task?" });
    await user.click(within(confirm).getByRole("button", { name: "Delete task" }));
    await waitFor(() => {
      expect(sent.some((r) => r.method === "DELETE" && r.path.endsWith(T3))).toBe(true);
    });
  });

  it("offers a Read-only member the list only", async () => {
    renderApp(URL, workspace(READER));
    expect(await screen.findByRole("checkbox", { name: "Complete Call back Sam" })).toBeDisabled();
    expect(screen.queryByLabelText("New task")).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete Plan the demo" })).toBeNull();
  });
});
