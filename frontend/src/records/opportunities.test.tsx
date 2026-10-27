import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Opportunities (decision P4-B): the board's columns come from the
 * pipeline, their counts and totals from the summary, the cards from the
 * list; the table reads the same list; creating sends exact decimal
 * strings with an idempotency key; the drawer moves stages, marks won or
 * lost (with a reason) and reopens, each with the version it holds; what
 * each role is offered follows `/access`. The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const PIPE = "b0000000-0000-4000-8000-000000000001";
const S1 = "c0000000-0000-4000-8000-000000000001";
const S2 = "c0000000-0000-4000-8000-000000000002";
const DEAL = "d0000000-0000-4000-8000-000000000001";
const OTHER = "d0000000-0000-4000-8000-000000000002";
const stamp = "2026-10-27T09:30:00+00:00";
const STAGES = [
  { id: S1, name: "Qualified", probability: 20, position: 0 },
  { id: S2, name: "Proposal", probability: 60, position: 1 },
];

function deal(extra: Record<string, unknown> = {}) {
  return {
    id: DEAL,
    title: "Website redesign",
    amount: "12500.50",
    currency: "EUR",
    weighted_amount: "2500.10",
    pipeline_id: PIPE,
    stage_id: S1,
    stage: STAGES[0],
    stage_entered_at: "2026-10-01T09:30:00+00:00",
    owner_user_id: "u-me",
    expected_close_date: "2026-12-15",
    contact_id: null,
    contact: null,
    company_id: null,
    company: { id: "e0000000-0000-4000-8000-000000000001", name: "Acme", archived: false },
    outcome: "open",
    lost_reason: null,
    closed_at: null,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: "u-me",
    updated_by_user_id: "u-me",
    version: 3,
    ...extra,
  };
}

const other = deal({
  id: OTHER,
  title: "Support plan",
  amount: null,
  weighted_amount: null,
  stage_id: S2,
  stage: STAGES[1],
  stage_entered_at: new Date().toISOString(),
  company: null,
  expected_close_date: null,
  owner_user_id: null,
});

function event(id: string, extra: Record<string, unknown>) {
  return {
    id,
    kind: "created",
    actor_user_id: "u-me",
    occurred_at: stamp,
    fields: null,
    stage_from: null,
    stage_to: null,
    stage_from_name: null,
    stage_to_name: null,
    stage_cause: null,
    owner_from: null,
    owner_to: null,
    outcome_from: null,
    outcome_to: null,
    ...extra,
  };
}

const HISTORY = [
  event("f1", {
    kind: "stage_changed",
    stage_from: S2,
    stage_to: S1,
    stage_from_name: "Proposal",
    stage_to_name: "Qualified",
    stage_cause: "stage_removed",
  }),
  event("f0", { stage_to: S2, stage_to_name: "Proposal" }),
];

type Reply = { status: number; body?: unknown } | undefined;

interface Options {
  actions: Record<string, boolean>;
  current?: Record<string, unknown>;
  onWrite?: (method: string, path: string, body: unknown) => Reply;
}

function workspace({ actions, current = deal(), onWrite }: Options): Handler {
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
    if (path === `${base}/settings`) {
      return {
        status: 200,
        body: {
          locale: "en",
          time_zone: "Europe/Amsterdam",
          currency: "EUR",
          version: 1,
          updated_at: stamp,
          updated_by_user_id: null,
        },
      };
    }
    if (path === `${base}/pipelines`) {
      const pipeline = { id: PIPE, name: "Sales", version: 1, created_at: stamp, updated_at: stamp, stages: STAGES };
      return { status: 200, body: { items: [pipeline], max_stages: 15 } };
    }
    if (method === "GET" && path.startsWith(`${base}/opportunities/summary`)) {
      const totals = [{ currency: "EUR", amount: "40000.00", weighted_amount: "8000.00" }];
      return {
        status: 200,
        body: {
          stages: [
            { stage_id: S1, count: 4, totals },
            { stage_id: S2, count: 1, totals: [] },
          ],
          total_capped: false,
        },
      };
    }
    if (method === "GET" && path.startsWith(`${base}/opportunities?`)) {
      return { status: 200, body: { items: [current, other], next_cursor: null, total: 2, total_capped: false } };
    }
    if (method === "GET" && path === `${base}/opportunities/${DEAL}`) return { status: 200, body: current };
    if (method === "GET" && path.startsWith(`${base}/opportunities/${DEAL}/history`)) {
      return { status: 200, body: { items: HISTORY, next_cursor: null } };
    }
    if (method !== "GET" && path.startsWith(`${base}/opportunities`)) return onWrite?.(method, path, body);
    return undefined;
  };
}

const OWNER = {
  read_members: true,
  create_opportunity: true,
  update_opportunity: true,
  delete_opportunity: true,
};
const READER = { read_members: true, create_opportunity: false, update_opportunity: false, delete_opportunity: false };
const URL = `/w/${WS}/opportunities`;

describe("opportunities board", () => {
  it("shows a column per stage with the summary's counts and totals, and open deals as cards", async () => {
    const { sent } = renderApp(URL, workspace({ actions: OWNER }));
    const board = await screen.findByRole("list", { name: "Board" });
    const qualified = await within(board).findByRole("listitem", { name: /Qualified/ });
    expect(qualified).toHaveTextContent("4");
    expect(qualified).toHaveTextContent("€40,000.00");
    expect(qualified).toHaveTextContent("20% probability");
    expect(within(qualified).getByRole("button", { name: "Website redesign" })).toBeInTheDocument();
    expect(qualified).toHaveTextContent("€12,500.50");
    expect(qualified).toHaveTextContent(/\d+d idle/);
    const proposal = within(board).getByRole("listitem", { name: /Proposal/ });
    expect(within(proposal).getByRole("button", { name: "Support plan" })).toBeInTheDocument();
    expect(screen.getByText("Open deals").nextSibling).toHaveTextContent("5");
    const listCall = sent.find((r) => r.path.startsWith(`/v1/workspaces/${WS}/opportunities?`));
    expect(new URLSearchParams(listCall?.path.split("?")[1]).getAll("outcome")).toEqual(["open"]);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("offers nothing to change to a Read-only member", async () => {
    const user = userEvent.setup();
    renderApp(URL, workspace({ actions: READER }));
    await screen.findByRole("list", { name: "Board" });
    expect(screen.queryByRole("button", { name: "New opportunity" })).toBeNull();
    expect(screen.getByText("You can view opportunities; changing them needs another role.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Website redesign" }));
    const drawer = await screen.findByRole("dialog", { name: "Opportunity" });
    expect(await within(drawer).findByRole("button", { name: "Move to Proposal" })).toBeDisabled();
    expect(within(drawer).queryByRole("button", { name: "Mark won" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Delete deal" })).toBeNull();
  });

  it("filters idle deals with the same parameters for the list and the summary", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace({ actions: OWNER }));
    await screen.findByRole("list", { name: "Board" });
    await user.click(screen.getByRole("button", { name: "Idle 7+ days" }));
    await waitFor(() => {
      const calls = sent.filter((r) => r.path.includes("idle=true"));
      expect(calls.some((r) => r.path.includes("/opportunities?"))).toBe(true);
      expect(calls.some((r) => r.path.includes("/opportunities/summary?"))).toBe(true);
    });
  });
});

describe("opportunities table", () => {
  it("lists deals with sortable columns and outcome choices", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace({ actions: OWNER }));
    await screen.findByRole("list", { name: "Board" });
    await user.click(screen.getByRole("button", { name: "Table" }));
    const table = await screen.findByRole("table", { name: "Opportunities" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(table).toHaveTextContent("€12,500.50");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(table).getByRole("button", { name: "Value" }));
    await user.click(screen.getByRole("button", { name: "Won" }));
    await waitFor(() => {
      const last = sent.filter((r) => r.path.includes("/opportunities?")).at(-1);
      const query = new URLSearchParams(last?.path.split("?")[1]);
      expect(query.get("sort")).toBe("amount");
      expect(query.getAll("outcome")).toEqual(["won"]);
    });
  });
});

describe("creating a deal", () => {
  it("checks the name and the value's decimals before sending, then sends exact strings", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      URL,
      workspace({
        actions: OWNER,
        onWrite: (method) => (method === "POST" ? { status: 201, body: deal() } : undefined),
      }),
    );
    await screen.findByRole("list", { name: "Board" });
    await user.click(screen.getByRole("button", { name: "New opportunity" }));
    const dialog = await screen.findByRole("dialog", { name: "New opportunity" });
    await user.click(within(dialog).getByRole("button", { name: "Create opportunity" }));
    expect(within(dialog).getByText("Give the opportunity a name.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Opportunity name"), "Website redesign");
    await user.type(within(dialog).getByLabelText("Value (EUR)"), "10.505");
    await user.click(within(dialog).getByRole("button", { name: "Create opportunity" }));
    expect(within(dialog).getByText(/no more decimals than EUR has/)).toBeInTheDocument();
    expect(sent.some((r) => r.method === "POST")).toBe(false);
    expect(await accessibilityViolations()).toEqual([]);

    const value = within(dialog).getByLabelText("Value (EUR)");
    await user.clear(value);
    await user.type(value, "12 500.5");
    await user.selectOptions(within(dialog).getByLabelText("Stage"), S2);
    await user.type(within(dialog).getByLabelText("Expected close"), "2026-12-15");
    await user.click(within(dialog).getByRole("button", { name: "Create opportunity" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        title: "Website redesign",
        amount: "12500.5",
        stage_id: S2,
        owner_user_id: "u-me",
        expected_close_date: "2026-12-15",
        contact_id: null,
        company_id: null,
      });
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe("the deal drawer", () => {
  it("moves the stage and marks the deal lost with a reason, sending its version", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `${URL}?record=${DEAL}`,
      workspace({ actions: OWNER, onWrite: () => ({ status: 200, body: deal({ version: 4 }) }) }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Opportunity" });
    expect(await within(drawer).findByText("€12,500.50")).toBeInTheDocument();
    expect(drawer).toHaveTextContent("20% probability · weighted €2,500.10");
    expect(
      await within(drawer).findByText("Moved from Proposal to Qualified when Proposal was removed"),
    ).toBeInTheDocument();
    expect(within(drawer).getByText("Created in Proposal")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Move to Qualified" })).toHaveAttribute("aria-pressed", "true");
    expect(await accessibilityViolations()).toEqual([]);

    await user.click(within(drawer).getByRole("button", { name: "Move to Proposal" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ stage_id: S2 });
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"3"');

    await user.click(within(drawer).getByRole("button", { name: "Mark lost" }));
    const lost = await screen.findByRole("dialog", { name: "Mark this deal lost?" });
    await user.click(within(lost).getByRole("button", { name: "Mark lost" }));
    expect(within(lost).getByText("Say why the deal was lost.")).toBeInTheDocument();
    await user.type(within(lost).getByLabelText("Reason lost"), "  Chose a competitor ");
    await user.click(within(lost).getByRole("button", { name: "Mark lost" }));
    await waitFor(() => {
      const outcome = sent.find((r) => r.method === "POST" && r.path.endsWith("/outcome"));
      expect(outcome?.body).toEqual({ outcome: "lost", lost_reason: "Chose a competitor" });
    });
  });

  it("shows a closed deal's outcome, keeps its stage, and offers Reopen", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `${URL}?record=${DEAL}`,
      workspace({
        actions: OWNER,
        current: deal({ outcome: "lost", lost_reason: "Budget cut", closed_at: stamp, weighted_amount: null }),
        onWrite: () => ({ status: 200, body: deal() }),
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Opportunity" });
    expect(await within(drawer).findByText("Budget cut")).toBeInTheDocument();
    expect(drawer).toHaveTextContent("Lost");
    expect(within(drawer).getByRole("button", { name: "Move to Proposal" })).toBeDisabled();
    expect(within(drawer).queryByRole("button", { name: "Mark won" })).toBeNull();
    await user.click(within(drawer).getByRole("button", { name: "Reopen" }));
    await waitFor(() => {
      expect(sent.find((r) => r.path.endsWith("/outcome"))?.body).toEqual({ outcome: "open" });
    });
  });

  it("explains a change someone else made first", async () => {
    const user = userEvent.setup();
    renderApp(
      `${URL}?record=${DEAL}`,
      workspace({
        actions: OWNER,
        onWrite: () => ({ status: 409, body: { detail: { code: "stale_version", current_version: 5 } } }),
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Opportunity" });
    await user.click(await within(drawer).findByRole("button", { name: "Mark won" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("Someone else changed this deal.");
  });
});
