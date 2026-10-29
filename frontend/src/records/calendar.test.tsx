import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { addDays, lanes, startOfDay, viewDays } from "../api/appointments";
import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Calendar (decision P5-A): the week grid with today's appointments, booking
 * with the live conflict check ("Book anyway" sends `allow_conflict`), the
 * drawer's status buttons and the confirmed cancel, what a Read-only member
 * sees, and the month view; business hours (decision P5-B) hatch closed
 * time, give each member a status line and warn before booking outside
 * them. The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const APPT = "a1000000-0000-4000-8000-000000000001";

function at(hour: number, minute = 0, days = 0): string {
  const moment = addDays(startOfDay(new Date()), days);
  moment.setHours(hour, minute, 0, 0);
  return moment.toISOString();
}

function appointment(extra: Record<string, unknown> = {}) {
  return {
    id: APPT,
    title: "Intro call with Sam",
    starts_at: at(10),
    ends_at: at(10, 30),
    kind: "video",
    location: "https://meet.example.test/sam",
    note: null,
    status: "confirmed",
    host_user_id: ME,
    contact_id: "c1",
    contact: { id: "c1", name: "Sam Jansen", archived: false },
    cancelled_at: null,
    cancelled_by_user_id: null,
    created_at: at(8),
    updated_at: at(8),
    created_by_user_id: ME,
    updated_by_user_id: ME,
    version: 2,
    ...extra,
  };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: {
    items?: unknown[];
    conflicts?: unknown[];
    outsideHours?: boolean;
    open?: { starts_at: string; ends_at: string }[];
    onWrite?: (method: string, path: string, body: unknown) => Reply;
  } = {},
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: {
          items: [{ user_id: ME, status: "active", roles: ["Owner"], membership_id: "m1" }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      };
    }
    const appointments = `${base}/appointments`;
    if (method === "GET" && path.startsWith(`${appointments}/upcoming`)) {
      return { status: 200, body: { items: options.items ?? [appointment()] } };
    }
    if (method === "GET" && path.startsWith(`${appointments}/conflicts`)) {
      return { status: 200, body: { conflicts: options.conflicts ?? [], outside_hours: options.outsideHours ?? false } };
    }
    if (method === "GET" && path.startsWith(`${appointments}/availability`)) {
      return {
        status: 200,
        body: { hours_set: options.open !== undefined, time_zone: "Europe/Amsterdam", open: options.open ?? [] },
      };
    }
    if (method === "GET" && path === `${appointments}/${APPT}`) return { status: 200, body: appointment() };
    if (method === "GET" && path.startsWith(`${appointments}?`)) {
      return { status: 200, body: { items: options.items ?? [appointment()], truncated: false } };
    }
    if (method !== "GET" && path.startsWith(appointments)) return options.onWrite?.(method, path, body);
    return undefined;
  };
}

const MANAGER = {
  read_members: true,
  create_appointment: true,
  update_appointment: true,
  delete_appointment: true,
};
const READER = { read_members: true, create_appointment: false, update_appointment: false, delete_appointment: false };

describe("calendar", () => {
  it("shows the week with today's appointments in the viewer's time zone", async () => {
    renderApp(`/w/${WS}/calendar`, workspace(MANAGER));
    const events = await screen.findAllByRole("button", { name: /Intro call with Sam.*Sam Jansen/ });
    // The grid's event, and the same appointment under "Up next".
    expect(events.filter((e) => e.classList.contains("calendar-event"))).toHaveLength(1);
    expect(events.find((e) => e.classList.contains("calendar-event"))).toHaveClass("confirmed");
    expect(screen.getByText(/^Times in /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Week", pressed: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New appointment" })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("books over a conflict only when asked to, with an idempotency key", async () => {
    const user = userEvent.setup();
    const conflict = { id: APPT, title: "Intro call with Sam", starts_at: at(10), ends_at: at(10, 30) };
    const { sent, headersSent } = renderApp(
      `/w/${WS}/calendar`,
      workspace(MANAGER, {
        conflicts: [conflict],
        onWrite: (method) => (method === "POST" ? { status: 201, body: appointment({ id: "new" }) } : undefined),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "New appointment" }));
    const dialog = await screen.findByRole("dialog", { name: "New appointment" });
    await user.type(within(dialog).getByLabelText("Title"), "Quote review");
    expect(await within(dialog).findByText(/already has an appointment/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Intro call with Sam/)).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Book anyway" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
      title: "Quote review",
      host_user_id: ME,
      kind: "in_person",
      status: "confirmed",
      allow_conflict: true,
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
  });

  it("books without overriding when the host is free", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/calendar`,
      workspace(MANAGER, {
        onWrite: (method) => (method === "POST" ? { status: 201, body: appointment({ id: "new" }) } : undefined),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "New appointment" }));
    const dialog = await screen.findByRole("dialog", { name: "New appointment" });
    await user.type(within(dialog).getByLabelText("Title"), "Demo");
    await user.click(within(dialog).getByRole("radio", { name: "Phone" }));
    expect(await within(dialog).findByText("The host is free at this time.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Book appointment" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({ kind: "phone", allow_conflict: false });
  });

  it("changes the status with the version and cancels only after confirming", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/calendar?record=${APPT}`,
      workspace(MANAGER, {
        onWrite: (method) => (method === "PATCH" ? { status: 200, body: appointment({ version: 3 }) } : undefined),
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Appointment" });
    expect(await within(drawer).findByText("Intro call with Sam")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Completed" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ status: "completed", allow_conflict: false });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"2"');

    await user.click(within(drawer).getByRole("button", { name: "Cancel appointment" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Cancel this appointment?" });
    expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    await user.click(within(confirm).getByRole("button", { name: "Cancel appointment" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(2);
    });
    expect(sent.filter((r) => r.method === "PATCH")[1]?.body).toEqual({ status: "cancelled", allow_conflict: false });
  });

  it("offers a Read-only member the calendar without changes", async () => {
    renderApp(`/w/${WS}/calendar?record=${APPT}`, workspace(READER));
    const drawer = await screen.findByRole("dialog", { name: "Appointment" });
    expect(await within(drawer).findByRole("button", { name: "Confirmed" })).toBeDisabled();
    expect(within(drawer).queryByRole("button", { name: "Cancel appointment" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New appointment" })).toBeNull();
  });

  it("shows at most three appointments a day in the month view", async () => {
    const user = userEvent.setup();
    const items = [9, 11, 13, 15].map((hour, i) =>
      appointment({ id: `a${String(i)}`, title: `Call ${String(i)}`, starts_at: at(hour), ends_at: at(hour, 30) }),
    );
    renderApp(`/w/${WS}/calendar`, workspace(MANAGER, { items }));
    await user.click(await screen.findByRole("button", { name: "Month" }));
    expect(await screen.findByText("+1 more")).toBeInTheDocument();
    const chips = document.querySelectorAll(".calendar-chip");
    expect([...chips].map((chip) => chip.textContent)).toEqual([
      expect.stringContaining("Call 0"),
      expect.stringContaining("Call 1"),
      expect.stringContaining("Call 2"),
    ]);
  });
});

describe("business hours on the calendar", () => {
  // Open 09:00-17:00 every day of this week, in the viewer's own zone.
  const open = Array.from({ length: 14 }, (_, i) => ({ starts_at: at(9, 0, i - 7), ends_at: at(17, 0, i - 7) }));

  it("hatches closed time, names it in the legend and gives each member a status line", async () => {
    renderApp(`/w/${WS}/calendar`, workspace(MANAGER, { open }));
    expect(await screen.findByText("Outside business hours", { selector: "li" })).toBeInTheDocument();
    // Seven day columns, each closed before 09:00 and after 17:00.
    await waitFor(() => {
      expect(document.querySelectorAll(".calendar-closed")).toHaveLength(14);
    });
    const presence = document.querySelector(".calendar-presence");
    const hour = new Date().getHours();
    const busy = hour === 10 && new Date().getMinutes() < 30;
    // `toEqual`, so the asymmetric matcher applies between 10:00 and 10:30.
    expect(presence?.textContent).toEqual(
      busy ? expect.stringContaining("In an appointment until") : hour >= 9 && hour < 17 ? "Free now" : "Outside business hours",
    );
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("hatches nothing while the workspace has not set its hours", async () => {
    renderApp(`/w/${WS}/calendar`, workspace(MANAGER));
    await screen.findAllByRole("button", { name: /Intro call with Sam/ });
    expect(document.querySelectorAll(".calendar-closed")).toHaveLength(0);
    expect(screen.queryByText("Outside business hours", { selector: "li" })).toBeNull();
  });

  it("warns before booking outside business hours and still books", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/calendar`,
      workspace(MANAGER, {
        open,
        outsideHours: true,
        onWrite: (method) => (method === "POST" ? { status: 201, body: appointment({ id: "new" }) } : undefined),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "New appointment" }));
    const dialog = await screen.findByRole("dialog", { name: "New appointment" });
    await user.type(within(dialog).getByLabelText("Title"), "Late call");
    expect(await within(dialog).findByText(/outside the business hours/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Book appointment" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({ allow_conflict: false });
  });
});

describe("calendar arithmetic", () => {
  it("places overlapping appointments side by side", () => {
    const placed = lanes([
      appointment({ id: "a", starts_at: at(9), ends_at: at(10) }),
      appointment({ id: "b", starts_at: at(9, 30), ends_at: at(10, 30) }),
      appointment({ id: "c", starts_at: at(10), ends_at: at(11) }),
    ] as never);
    expect(placed.map((p) => [p.appointment.id, p.lane, p.lanes])).toEqual([
      ["a", 0, 2],
      ["b", 1, 2],
      ["c", 0, 2],
    ]);
  });

  it("starts weeks on Monday and covers whole weeks of a month", () => {
    const week = viewDays("week", new Date(2026, 9, 28));
    expect(week[0]?.getDay()).toBe(1);
    expect(week).toHaveLength(7);
    const month = viewDays("month", new Date(2026, 9, 15));
    expect(month[0]?.getDay()).toBe(1);
    expect(month.length % 7).toBe(0);
    expect(month.some((d) => d.getMonth() === 9 && d.getDate() === 31)).toBe(true);
  });
});
