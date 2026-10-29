import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * The Home page (decision P4-D): the attention strip, the four headline
 * numbers, the pipeline by stage, today's appointments and tasks (completing
 * one in place), recent activity, a card failing on its own, and a workspace
 * opening on Home. The server computes every number; these tests check the
 * page shows what it is given and asks with the right filters.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const S1 = "51000000-0000-4000-8000-000000000001";
const S2 = "51000000-0000-4000-8000-000000000002";
const T1 = "71000000-0000-4000-8000-000000000001";
const stamp = "2026-10-28T09:30:00+00:00";

function at(hour: number, minute = 0): string {
  const day = new Date();
  day.setHours(hour, minute, 0, 0);
  return day.toISOString();
}

const MANAGER = { read_members: true, update_task: true, create_task: true };
const READER = { read_members: true, update_task: false };

const STAGES = [
  { id: S1, name: "Qualified", probability: 20, position: 0 },
  { id: S2, name: "Proposal", probability: 60, position: 1 },
];

const TASK = {
  id: T1,
  title: "Call back Sam",
  priority: "high",
  due_at: at(0, 30),
  assignee_user_id: ME,
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
  created_by_user_id: ME,
  updated_by_user_id: ME,
  version: 3,
};

const APPOINTMENT = {
  id: "a1000000-0000-4000-8000-000000000001",
  title: "Intro call with Sam",
  starts_at: at(10),
  ends_at: at(10, 30),
  kind: "video",
  location: null,
  note: null,
  status: "confirmed",
  host_user_id: ME,
  contact_id: "c1",
  contact: { id: "c1", name: "Sam Jansen", archived: false },
  booking: null,
  cancelled_at: null,
  cancelled_by_user_id: null,
  created_at: stamp,
  updated_at: stamp,
  created_by_user_id: ME,
  updated_by_user_id: ME,
  version: 1,
};

const FEED = [
  {
    id: "e1",
    kind: "created",
    occurred_at: stamp,
    actor_user_id: ME,
    fields: null,
    stage_from: null,
    stage_to: null,
    owner_from: null,
    owner_to: null,
    company_id: null,
    company_name: null,
    note_id: null,
    note_excerpt: null,
    note_truncated: false,
    record_type: "contact",
    record_id: "c1000000-0000-4000-8000-000000000001",
    record_name: "Sam Jansen",
  },
];

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: {
    failFeed?: boolean;
    onWrite?: (method: string, path: string, body: unknown) => Reply;
  } = {},
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return options.onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: { membership_id: "m1", roles: ["Owner"], actions },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: { items: [], total: 0, limit: 50, offset: 0 },
      };
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
      const pipeline = {
        id: "p1",
        name: "Sales",
        version: 1,
        created_at: stamp,
        updated_at: stamp,
        stages: STAGES,
      };
      return { status: 200, body: { items: [pipeline], max_stages: 15 } };
    }
    if (path.startsWith(`${base}/opportunities/summary`)) {
      if (path.includes("idle=true")) {
        return {
          status: 200,
          body: {
            stages: [{ stage_id: S1, count: 2, totals: [] }],
            total_capped: false,
          },
        };
      }
      return {
        status: 200,
        body: {
          stages: [
            {
              stage_id: S1,
              count: 4,
              totals: [
                {
                  currency: "EUR",
                  amount: "10000.00",
                  weighted_amount: "2000.00",
                },
              ],
            },
            {
              stage_id: S2,
              count: 1,
              totals: [
                {
                  currency: "EUR",
                  amount: "30000.00",
                  weighted_amount: "18000.00",
                },
              ],
            },
          ],
          total_capped: false,
        },
      };
    }
    if (path.startsWith(`${base}/opportunities?`)) {
      return {
        status: 200,
        body: { items: [], next_cursor: null, total: 0, total_capped: false },
      };
    }
    if (path.startsWith(`${base}/contacts?`)) {
      return {
        status: 200,
        body: { items: [], next_cursor: null, total: 12, total_capped: false },
      };
    }
    if (path.startsWith(`${base}/tasks/counts`)) {
      return { status: 200, body: { open: 5, mine: 3, overdue: 2, done: 1 } };
    }
    if (path.startsWith(`${base}/tasks?`)) {
      return {
        status: 200,
        body: {
          items: [TASK],
          next_cursor: null,
          total: 1,
          total_capped: false,
        },
      };
    }
    if (path.startsWith(`${base}/appointments?`)) {
      return { status: 200, body: { items: [APPOINTMENT], truncated: false } };
    }
    if (path.startsWith(`${base}/activity?`)) {
      return options.failFeed
        ? { status: 403, body: {} }
        : { status: 200, body: { items: FEED } };
    }
    return undefined;
  };
}

const GREETING = /^Good (morning|afternoon|evening)$/;

describe("the Home page", () => {
  it("shows what needs attention, the headline numbers and today's work", async () => {
    const { sent } = renderApp(`/w/${WS}/home`, workspace(MANAGER));
    expect(
      await screen.findByRole("heading", { level: 1, name: GREETING }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Here's how Acme is doing, and what needs attention today.",
      ),
    ).toBeInTheDocument();

    const attention = screen.getByRole("region", {
      name: "Needs your attention",
    });
    expect(
      await within(attention).findByRole("button", { name: "2 Overdue tasks" }),
    ).toBeInTheDocument();
    expect(
      await within(attention).findByRole("button", {
        name: "2 Deals idle 7+ days",
      }),
    ).toBeInTheDocument();

    const kpis = screen.getByRole("region", { name: "Headline numbers" });
    expect(
      await within(kpis).findByRole("button", { name: /^Contacts\s*12$/ }),
    ).toBeInTheDocument();
    expect(
      within(kpis).getByRole("button", { name: /^Open deals\s*5$/ }),
    ).toBeInTheDocument();
    expect(
      within(kpis).getByRole("button", {
        name: /Pipeline value\s*€40,000\.00\s*Weighted €20,000\.00/,
      }),
    ).toBeInTheDocument();
    expect(
      within(kpis).getByRole("button", {
        name: /^Open tasks\s*5\s*2 overdue$/,
      }),
    ).toBeInTheDocument();

    const pipeline = screen.getByRole("region", { name: "Pipeline by stage" });
    const stages = await within(pipeline).findAllByRole("listitem");
    expect(stages[0]).toHaveTextContent("Qualified · 4€10,000.00");
    expect(stages[1]).toHaveTextContent("Proposal · 1€30,000.00");

    const appointments = screen.getByRole("region", {
      name: "Today's appointments",
    });
    expect(
      await within(appointments).findByText("Intro call with Sam"),
    ).toBeInTheDocument();
    expect(within(appointments).getByText("Confirmed")).toBeInTheDocument();

    const tasks = screen.getByRole("region", { name: "Tasks due today" });
    expect(await within(tasks).findByText("Call back Sam")).toBeInTheDocument();

    const activity = screen.getByRole("region", { name: "Activity" });
    expect(
      await within(activity).findByRole("button", { name: "Sam Jansen" }),
    ).toBeInTheDocument();
    expect(within(activity).getByText(/Created/)).toBeInTheDocument();

    // Open deals only; the idle count asks for idle deals; tasks due before tomorrow.
    const summaries = sent.filter((r) =>
      r.path.includes("/opportunities/summary?"),
    );
    expect(
      summaries.some(
        (r) => r.path.includes("outcome=open") && !r.path.includes("idle"),
      ),
    ).toBe(true);
    expect(
      summaries.some(
        (r) => r.path.includes("outcome=open") && r.path.includes("idle=true"),
      ),
    ).toBe(true);
    expect(
      sent.some(
        (r) => r.path.includes("/tasks?") && r.path.includes("due_to="),
      ),
    ).toBe(true);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("opens the overdue tasks from the attention strip", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/home`, workspace(MANAGER));
    await user.click(
      await screen.findByRole("button", { name: "2 Overdue tasks" }),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Tasks" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Overdue/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens the idle deals from the attention strip", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/home`, workspace(MANAGER));
    await user.click(
      await screen.findByRole("button", { name: "2 Deals idle 7+ days" }),
    );
    expect(
      await screen.findByRole("button", { name: "Idle 7+ days" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("completes a task in place with its version", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/home`,
      workspace(MANAGER, {
        onWrite: () => ({
          status: 200,
          body: { ...TASK, done: true, version: 4 },
        }),
      }),
    );
    await user.click(
      await screen.findByRole("checkbox", { name: "Complete Call back Sam" }),
    );
    expect(await screen.findByText("Task completed.")).toBeInTheDocument();
    const patch = sent.find((r) => r.method === "PATCH");
    expect(patch?.path).toBe(`/v1/workspaces/${WS}/tasks/${T1}`);
    expect(patch?.body).toEqual({ done: true });
    expect(
      headersSent.find((r) => r.method === "PATCH")?.headers["if-match"],
    ).toBe('"3"');
  });

  it("lets a Read-only member look but not complete", async () => {
    renderApp(`/w/${WS}/home`, workspace(READER));
    const box = await screen.findByRole("checkbox", {
      name: "Complete Call back Sam",
    });
    await waitFor(() => {
      expect(box).toBeDisabled();
    });
  });

  it("keeps the other cards when one fails", async () => {
    renderApp(`/w/${WS}/home`, workspace(MANAGER, { failFeed: true }));
    const activity = await screen.findByRole("region", { name: "Activity" });
    expect(await within(activity).findByRole("alert")).toHaveTextContent(
      "You do not have permission to see this.",
    );
    expect(
      await screen.findByRole("button", { name: /^Contacts\s*12$/ }),
    ).toBeInTheDocument();
  });

  it("asks a signed-out member to sign in once, not on every card", async () => {
    renderApp(`/w/${WS}/home`, (_, path) =>
      path === "/auth/me"
        ? { status: 200, body: { user_id: ME } }
        : { status: 401, body: { detail: "Not authenticated" } },
    );
    expect(
      await screen.findByRole("link", { name: "Sign in" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(
      screen.queryByRole("region", { name: "Headline numbers" }),
    ).toBeNull();
  });

  it("is where a workspace opens", async () => {
    renderApp(`/w/${WS}`, workspace(MANAGER));
    expect(
      await screen.findByRole("heading", { level: 1, name: GREETING }),
    ).toBeInTheDocument();
  });
});
