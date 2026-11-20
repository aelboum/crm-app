import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * The contact brief (decision P9-B): only members with `use_ai_brief` see
 * the section; a brief is asked for on a press, shown as a suggestion, and
 * each state the server answers has its own plain message. The server and
 * SaaS-OS enforce every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const SAM = "d0000000-0000-4000-8000-000000000001";
const stamp = "2026-10-28T09:30:00+00:00";

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

type Reply = { status: number; body?: unknown };

function workspace(actions: Record<string, boolean>, brief?: Reply): Handler {
  return (method, path) => {
    const base = `/v1/workspaces/${WS}`;
    if (method === "POST" && path === `${base}/contacts/${SAM}/brief`) return brief;
    if (method !== "GET") return undefined;
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Member"], actions } };
    }
    if (path.startsWith(`${base}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (path.startsWith(`${base}/contacts?`)) {
      return { status: 200, body: { items: [sam], next_cursor: null, total: 1, total_capped: false } };
    }
    if (path === `${base}/contacts/${SAM}`) return { status: 200, body: sam };
    return undefined;
  };
}

const ALLOWED = { read_members: true, use_ai_brief: true };

async function briefSection() {
  return screen.findByRole("region", { name: "AI brief" });
}

describe("contact brief", () => {
  it("shows a brief as a suggestion and sends nothing until asked", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(ALLOWED, {
        status: 200,
        body: { state: "ready", text: "A new lead.\nCall this week." },
      }),
    );
    const section = await briefSection();
    expect(within(section).getByText(/never names, contact details/)).toBeInTheDocument();
    expect(sent.some((r) => r.method === "POST")).toBe(false);
    await user.click(within(section).getByRole("button", { name: "Write a brief" }));
    expect(await within(section).findByText(/Call this week\./)).toBeInTheDocument();
    expect(within(section).getByText("Suggestion: check it before acting on it.")).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Write it again" })).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("says when AI is off for the workspace", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(ALLOWED, { status: 200, body: { state: "unavailable", text: null } }),
    );
    const section = await briefSection();
    await user.click(within(section).getByRole("button", { name: "Write a brief" }));
    expect(
      await within(section).findByText(/AI is not turned on for this workspace/),
    ).toBeInTheDocument();
  });

  it("says when the budget is used up", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(ALLOWED, { status: 200, body: { state: "quota_reached", text: null } }),
    );
    const section = await briefSection();
    await user.click(within(section).getByRole("button", { name: "Write a brief" }));
    expect(await within(section).findByText(/used its AI budget/)).toBeInTheDocument();
  });

  it("treats a refused request as a failure", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(ALLOWED, { status: 404, body: { detail: { code: "not_found" } } }),
    );
    const section = await briefSection();
    await user.click(within(section).getByRole("button", { name: "Write a brief" }));
    expect(await within(section).findByText(/could not be written/)).toBeInTheDocument();
  });

  it("is not offered to a member who may not use AI", async () => {
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace({ read_members: true }));
    // The drawer is open: its tasks section shows, the brief section does not.
    expect(await screen.findByRole("region", { name: /Open tasks/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "AI brief" })).toBeNull();
  });
});
