import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { fileDownload } from "../api/exportContacts";
import { daysBefore, daysIn, todayIn } from "../api/reports";
import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Reports (decision P10-A): the page asks each report for a period of whole
 * days ending today in the workspace's time zone, shows every figure with
 * its definition and its comparison, refuses a custom period outside the
 * rules before asking, lets one failing report fail alone, says when a
 * report stopped at its row cap, and merges the team's rows. The server
 * counts and enforces everything.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const ADA = "bbbbbbbb-0000-4000-8000-000000000002";
const ZONE = "Pacific/Auckland";

function period(path: string) {
  const url = new URL(path, "http://x");
  return {
    start: url.searchParams.get("start"),
    end: url.searchParams.get("end"),
  };
}

const PERIOD = { start: "2026-10-01", end: "2026-10-31", days: 31 };

function reports(
  overrides: Record<string, { status: number; body?: unknown }> = {},
): Handler {
  return (method, path) => {
    const base = `/v1/workspaces/${WS}`;
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`)
      return {
        status: 200,
        body: { membership_id: "m1", roles: ["Owner"], actions: {} },
      };
    if (path === `${base}/settings`) {
      return {
        status: 200,
        body: {
          locale: "en",
          time_zone: ZONE,
          currency: "EUR",
          version: 1,
          updated_at: "2026-10-01T00:00:00Z",
          updated_by_user_id: null,
        },
      };
    }
    for (const [kind, reply] of Object.entries(overrides)) {
      if (path.startsWith(`${base}/reports/${kind}?`)) return reply;
    }
    if (path.startsWith(`${base}/reports/contacts?`)) {
      return {
        status: 200,
        body: {
          period: PERIOD,
          capped: false,
          created: 12,
          created_before: 9,
          sources: [
            { source: "form", count: 8 },
            { source: "manual", count: 4 },
          ],
        },
      };
    }
    if (path.startsWith(`${base}/reports/deals?`)) {
      return {
        status: 200,
        body: {
          period: PERIOD,
          capped: false,
          created: 5,
          created_before: 3,
          won: 2,
          won_before: 1,
          lost: 1,
          lost_before: 0,
          win_rate: 67,
          win_rate_before: 100,
          won_value: [
            { currency: "EUR", amount: "1000.50" },
            { currency: "USD", amount: "300.00" },
          ],
          lost_value: [{ currency: "EUR", amount: "200.00" }],
          owners: [
            {
              user_id: ME,
              won: 2,
              won_value: [{ currency: "EUR", amount: "1000.50" }],
            },
          ],
        },
      };
    }
    if (path.startsWith(`${base}/reports/tasks?`)) {
      return {
        status: 200,
        body: {
          period: PERIOD,
          capped: false,
          created: 3,
          created_before: 2,
          completed: 3,
          completed_before: 1,
          on_time: 1,
          late: 1,
          no_due: 1,
          overdue_now: 4,
          completed_by: [{ user_id: ADA, count: 3 }],
        },
      };
    }
    if (path.startsWith(`${base}/reports/appointments?`)) {
      return {
        status: 200,
        body: {
          period: PERIOD,
          capped: false,
          held: 3,
          held_before: 1,
          statuses: [
            { status: "completed", count: 1 },
            { status: "no_show", count: 1 },
          ],
          no_show_rate: 50,
          hosts: [{ user_id: ME, count: 3 }],
        },
      };
    }
    return method === "GET" ? undefined : { status: 405 };
  };
}

describe("reports", () => {
  it("shows the last 30 days in the workspace's time zone with definitions and comparisons", async () => {
    const { sent } = renderApp(`/w/${WS}/reports`, reports());
    expect(
      await screen.findByRole("heading", { level: 1, name: "Reports" }),
    ).toBeInTheDocument();
    const today = todayIn(ZONE);
    const asked = sent.filter((r) => r.path.includes("/reports/"));
    await waitFor(() => {
      expect(
        new Set(asked.map((r) => r.path.split("?")[0]?.split("/").pop())).size,
      ).toBe(4);
    });
    for (const call of asked) {
      expect(period(call.path)).toEqual({
        start: daysBefore(today, 29),
        end: today,
      });
    }
    const kpis = await screen.findByRole("region", {
      name: "Headline figures",
    });
    expect(await within(kpis).findByText("12")).toBeInTheDocument();
    expect(within(kpis).getByText("Previous 30 days: 9")).toBeInTheDocument();
    expect(within(kpis).getByText("67%")).toBeInTheDocument();
    const deals = screen.getByRole("region", { name: "Deal outcomes" });
    expect(
      within(deals).getByText(/€1,000\.50 · \$300\.00/),
    ).toBeInTheDocument();
    expect(
      within(deals).getByText(/a reopened deal is not counted/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Appointments" }),
    ).toHaveTextContent("No-show rate: 50%");
    expect(
      screen.getByRole("region", { name: "New contacts by source" }),
    ).toHaveTextContent("Form8");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("asks again for another preset", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/reports`, reports());
    await screen.findByRole("region", { name: "Headline figures" });
    await user.click(screen.getByRole("button", { name: "Last 7 days" }));
    expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const today = todayIn(ZONE);
    await waitFor(() => {
      expect(
        sent.some(
          (r) =>
            r.path.includes("/reports/deals?") &&
            period(r.path).start === daysBefore(today, 6),
        ),
      ).toBe(true);
    });
  });

  it("refuses a custom period outside the rules before asking, then asks for a valid one", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/reports`, reports());
    await screen.findByRole("region", { name: "Headline figures" });
    const form = screen.getByRole("form", { name: "Custom period" });
    const from = within(form).getByLabelText("From");
    const to = within(form).getByLabelText("To");
    await user.clear(from);
    await user.type(from, "2026-10-31");
    await user.clear(to);
    await user.type(to, "2026-10-01");
    await user.click(within(form).getByRole("button", { name: "Show" }));
    expect(within(form).getByRole("alert")).toHaveTextContent(
      "must not be before",
    );
    await user.clear(from);
    await user.type(from, "2024-01-01");
    await user.click(within(form).getByRole("button", { name: "Show" }));
    expect(within(form).getByRole("alert")).toHaveTextContent(
      "at most 366 days",
    );
    expect(sent.some((r) => r.path.includes("start=2024-01-01"))).toBe(false);
    await user.clear(from);
    await user.type(from, "2026-10-01");
    await user.clear(to);
    await user.type(to, "2026-10-31");
    await user.click(within(form).getByRole("button", { name: "Show" }));
    await waitFor(() => {
      expect(
        sent.some((r) =>
          r.path.includes("/reports/tasks?start=2026-10-01&end=2026-10-31"),
        ),
      ).toBe(true);
    });
    expect(
      screen.getByText(/^31 days, both dates included/),
    ).toBeInTheDocument();
  });

  it("lets one refused report fail alone and keeps the others", async () => {
    renderApp(
      `/w/${WS}/reports`,
      reports({ tasks: { status: 403, body: { detail: "Forbidden" } } }),
    );
    const tasks = await screen.findByRole("region", { name: "Tasks" });
    expect(await within(tasks).findByRole("alert")).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "Deal outcomes" }),
    ).toHaveTextContent("Created5");
    const team = screen.getByRole("region", { name: "Team" });
    // Ada only completed tasks, which this member may not see: she is not listed.
    expect(within(team).queryByText(/bbbbbbbb/)).toBeNull();
    expect(within(team).getAllByRole("row")[1]).toHaveTextContent("You");
  });

  it("says when a report stopped at its row cap", async () => {
    renderApp(
      `/w/${WS}/reports`,
      reports({
        contacts: {
          status: 200,
          body: {
            period: PERIOD,
            capped: true,
            created: 20000,
            created_before: 0,
            sources: [],
          },
        },
      }),
    );
    expect(
      await screen.findByText(/Only the first 20,000 records were counted/),
    ).toBeInTheDocument();
  });

  it("merges each member's deals, tasks and appointments", async () => {
    renderApp(`/w/${WS}/reports`, reports());
    const team = await screen.findByRole("region", { name: "Team" });
    const rows = await within(team).findAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent(/You2€1,000\.5003/);
    expect(rows[2]).toHaveTextContent(/Member bbbbbbbb0—30/);
  });

  it("downloads a card's figures as CSV for the chosen period", async () => {
    const user = userEvent.setup();
    const save = vi
      .spyOn(fileDownload, "save")
      .mockImplementation(() => undefined);
    const { sent } = renderApp(`/w/${WS}/reports`, (method, path, body) =>
      path.includes("/reports/deals/export.csv")
        ? { status: 200, body: "section,item,value,previous" }
        : reports()(method, path, body),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Download Deal outcomes as CSV",
      }),
    );
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
    const asked = sent.find((r) => r.path.includes("/export.csv"));
    expect(asked?.path).toMatch(
      /\/reports\/deals\/export\.csv\?start=\d{4}-\d{2}-\d{2}&end=\d{4}-\d{2}-\d{2}$/,
    );
    expect(save.mock.calls[0]?.[1]).toMatch(/^report-deals-.*\.csv$/);
    save.mockRestore();
  });
});

describe("report periods", () => {
  it("counts calendar days and steps back by calendar", () => {
    expect(daysIn({ start: "2026-10-01", end: "2026-10-31" })).toBe(31);
    expect(daysIn({ start: "2026-03-28", end: "2026-03-30" })).toBe(3);
    expect(daysBefore("2026-03-01", 1)).toBe("2026-02-28");
    expect(todayIn("Pacific/Auckland", new Date("2026-10-31T12:00:00Z"))).toBe(
      "2026-11-01",
    );
    expect(
      todayIn("America/Los_Angeles", new Date("2026-10-31T06:00:00Z")),
    ).toBe("2026-10-30");
  });
});
