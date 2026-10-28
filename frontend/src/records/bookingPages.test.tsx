import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { addDays, startOfDay } from "../api/appointments";
import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Booking pages (decision P5-C): the Calendar's Booking pages drawer (the
 * list, creating with an idempotency key, publishing refused without
 * business hours, what a Read-only member sees), the appointment drawer's
 * source row, the hosted page (free times by day in the visitor's zone,
 * what a booking sends, the confirmation with the private link, refusals
 * by field, a time taken meanwhile) and the visitor's own link (view and
 * cancel with the token in the body). The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const PAGE_ID = "b1000000-0000-4000-8000-000000000001";
const APPT = "a1000000-0000-4000-8000-000000000001";
const KEY = "Pi56P5vEua9wJ6F5KLStbg";
const TOKEN = "t".repeat(43);
const stamp = "2026-10-28T09:30:00+00:00";
const SLOT = /^\d{1,2}:\d{2}/;

function at(hour: number, minute = 0, days = 0): string {
  const moment = addDays(startOfDay(new Date()), days);
  moment.setHours(hour, minute, 0, 0);
  return moment.toISOString();
}

function page(extra: Record<string, unknown> = {}) {
  return {
    id: PAGE_ID,
    name: "Intro call",
    description: "Thirty minutes to get to know you.",
    status: "published",
    public_key: KEY,
    host_user_id: ME,
    length_minutes: 30,
    step_minutes: 30,
    kind: "video",
    location: "https://meet.example.test/intro",
    notice_minutes: 240,
    horizon_days: 30,
    booking_count: 2,
    last_booked_at: stamp,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: ME,
    updated_by_user_id: ME,
    version: 3,
    ...extra,
  };
}

function appointment(extra: Record<string, unknown> = {}) {
  return {
    id: APPT,
    title: "Intro call — Ada Lovelace",
    starts_at: at(10, 0, 1),
    ends_at: at(10, 30, 1),
    kind: "video",
    location: "https://meet.example.test/intro",
    note: "About the engine.",
    status: "confirmed",
    host_user_id: ME,
    contact_id: "c1",
    contact: { id: "c1", name: "Ada Lovelace", archived: false },
    booking: { page_id: PAGE_ID, page_name: "Intro call", cancelled_by_visitor: false },
    cancelled_at: null,
    cancelled_by_user_id: null,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: ME,
    updated_by_user_id: ME,
    version: 1,
    ...extra,
  };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: { appointment?: unknown; onWrite?: (method: string, path: string, body: unknown) => Reply } = {},
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
    if (method === "GET" && path.startsWith(`${appointments}/upcoming`)) return { status: 200, body: { items: [] } };
    if (method === "GET" && path.startsWith(`${appointments}/availability`)) {
      return { status: 200, body: { hours_set: false, time_zone: "UTC", open: [] } };
    }
    if (method === "GET" && path === `${appointments}/${APPT}`) {
      return { status: 200, body: options.appointment ?? appointment() };
    }
    if (method === "GET" && path.startsWith(`${appointments}?`)) {
      return { status: 200, body: { items: [], truncated: false } };
    }
    const pages = `${base}/booking-pages`;
    if (method === "GET" && path === pages) {
      return {
        status: 200,
        body: { items: [page(), page({ id: "b2", name: "Demo", status: "draft", booking_count: 0 })] },
      };
    }
    if (method !== "GET" && path.startsWith(pages)) return options.onWrite?.(method, path, body);
    return undefined;
  };
}

const MANAGER = {
  read_members: true,
  create_appointment: true,
  update_appointment: true,
  delete_appointment: true,
  read_booking_pages: true,
  manage_booking_pages: true,
};
const READER = { ...MANAGER, create_appointment: false, update_appointment: false, manage_booking_pages: false };

async function openDrawer(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Booking pages" }));
  return screen.findByRole("dialog", { name: "Booking pages" });
}

describe("booking pages in the calendar", () => {
  it("lists the pages with their status, link and bookings", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/calendar`, workspace(MANAGER));
    const drawer = await openDrawer(user);
    const [published, draft] = (await within(drawer).findAllByRole("listitem")) as [HTMLElement, HTMLElement];
    expect(published).toHaveTextContent("Intro call");
    expect(published).toHaveTextContent("Published");
    expect(published).toHaveTextContent("2 bookings");
    expect(within(published).getByRole("link")).toHaveAttribute("href", `/app/b/${WS}/${KEY}`);
    expect(draft).toHaveTextContent("Draft");
    expect(within(draft).queryByRole("link")).toBeNull();
    expect(within(draft).getByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("creates a draft with an idempotency key", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/calendar`,
      workspace(MANAGER, {
        onWrite: (method) => (method === "POST" ? { status: 201, body: page({ status: "draft" }) } : undefined),
      }),
    );
    const drawer = await openDrawer(user);
    await user.click(within(drawer).getByRole("button", { name: "New booking page" }));
    const dialog = await screen.findByRole("dialog", { name: "New booking page" });
    await user.type(within(dialog).getByLabelText("Name"), "  Intro call ");
    await user.selectOptions(within(dialog).getByLabelText("Length"), "45");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({
      name: "Intro call",
      description: null,
      host_user_id: ME,
      length_minutes: 45,
      step_minutes: 30,
      kind: "video",
      location: null,
      notice_minutes: 240,
      horizon_days: 30,
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
  });

  it("says where to set business hours when publishing is refused", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/calendar`,
      workspace(MANAGER, {
        onWrite: () => ({ status: 422, body: { detail: { code: "business_hours_required" } } }),
      }),
    );
    const drawer = await openDrawer(user);
    const draft = (await within(drawer).findAllByRole("listitem"))[1] as HTMLElement;
    await user.click(within(draft).getByRole("button", { name: "Publish" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent(/Settings › Business profile/);
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ status: "published" });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"3"');
  });

  it("offers a Read-only member the pages without changes", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/calendar`, workspace(READER));
    const drawer = await openDrawer(user);
    await within(drawer).findAllByRole("listitem");
    expect(within(drawer).queryByRole("button", { name: "New booking page" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Publish" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Delete" })).toBeNull();
    expect(within(drawer).getAllByRole("button", { name: "Copy link" })).toHaveLength(1);
  });

  it("names how an appointment was booked", async () => {
    renderApp(`/w/${WS}/calendar?record=${APPT}`, workspace(MANAGER));
    const drawer = await screen.findByRole("dialog", { name: "Appointment" });
    expect(await within(drawer).findByText("Booked online · Intro call")).toBeInTheDocument();
  });

  it("says when the visitor cancelled", async () => {
    const cancelled = appointment({
      status: "cancelled",
      cancelled_at: stamp,
      booking: { page_id: null, page_name: null, cancelled_by_visitor: true },
    });
    renderApp(`/w/${WS}/calendar?record=${APPT}`, workspace(MANAGER, { appointment: cancelled }));
    const drawer = await screen.findByRole("dialog", { name: "Appointment" });
    expect(await within(drawer).findByText(/Cancelled by the visitor\./)).toBeInTheDocument();
    expect(within(drawer).getByText("Booked online")).toBeInTheDocument();
  });
});

const PUBLIC = `/v1/public/booking-pages/${WS}/${KEY}`;
const BOOKINGS = `/v1/public/bookings/${WS}`;
const VIEW = {
  page_name: "Intro call",
  starts_at: at(9, 0, 1),
  ends_at: at(9, 30, 1),
  kind: "video",
  location: "https://meet.example.test/intro",
  cancelled: false,
  cancelled_by_visitor: false,
  can_cancel: true,
};

function visitor(
  options: { onBook?: (body: unknown) => Reply; page?: Reply; times?: () => string[] } = {},
): Handler {
  return (method, path, body) => {
    if (path === PUBLIC && method === "GET") {
      return (
        options.page ?? {
          status: 200,
          body: {
            name: "Intro call",
            description: "Thirty minutes to get to know you.",
            length_minutes: 30,
            kind: "video",
            time_zone: "UTC",
            horizon_days: 30,
          },
        }
      );
    }
    if (path.startsWith(`${PUBLIC}/times?`)) {
      return { status: 200, body: { times: options.times?.() ?? [at(9, 0, 1), at(9, 30, 1), at(14, 0, 2)] } };
    }
    if (path === PUBLIC && method === "POST") return options.onBook?.(body);
    return undefined;
  };
}

describe("hosted booking page", () => {
  it("books a free time and shows the private link once", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/b/${WS}/${KEY}`,
      visitor({ onBook: () => ({ status: 201, body: { booking: VIEW, token: TOKEN } }) }),
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Intro call" })).toBeInTheDocument();
    expect(screen.getByText(/^Times are shown in /)).toBeInTheDocument();
    const slots = await screen.findAllByRole("button", { name: SLOT });
    expect(slots).toHaveLength(3);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(slots[0] as HTMLElement);
    await user.type(screen.getByRole("textbox", { name: /First name/ }), "Ada");
    await user.type(screen.getByRole("textbox", { name: /Email/ }), "ada@example.test");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Book" }));
    expect(await screen.findByRole("heading", { name: "You are booked" })).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", expect.stringContaining(`/app/b/${WS}/manage#${TOKEN}`));
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({
      first_name: "Ada",
      last_name: null,
      email: "ada@example.test",
      phone: null,
      message: null,
      starts_at: at(9, 0, 1),
      website: "",
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    expect(sent.some((r) => r.path === "/auth/me")).toBe(false);
  });

  it("shows refusals next to their fields", async () => {
    const user = userEvent.setup();
    renderApp(
      `/b/${WS}/${KEY}`,
      visitor({
        onBook: () => ({
          status: 422,
          body: { detail: { code: "invalid_visitor", fields: { first_name: "invalid", email: "required" } } },
        }),
      }),
    );
    await user.click((await screen.findAllByRole("button", { name: SLOT }))[0] as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Book" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Some details need attention.");
    expect(screen.getByRole("textbox", { name: /First name/ })).toHaveAccessibleDescription("Check this value.");
    expect(screen.getByRole("textbox", { name: /Email/ })).toHaveAccessibleDescription("This field is required.");
  });

  it("goes back to the times when the time was taken meanwhile", async () => {
    const user = userEvent.setup();
    let loads = 0;
    const { sent } = renderApp(
      `/b/${WS}/${KEY}`,
      visitor({
        onBook: () => ({ status: 409, body: { detail: { code: "time_unavailable" } } }),
        times: () => {
          loads += 1;
          return loads === 1 ? [at(9, 0, 1), at(9, 30, 1)] : [at(9, 30, 1)];
        },
      }),
    );
    await user.click((await screen.findAllByRole("button", { name: SLOT }))[0] as HTMLElement);
    await user.type(screen.getByRole("textbox", { name: /First name/ }), "Ada");
    await user.type(screen.getByRole("textbox", { name: /Email/ }), "ada@example.test");
    await user.click(screen.getByRole("button", { name: "Book" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That time is no longer free.");
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: SLOT })).toHaveLength(1);
    });
    expect(sent.filter((r) => r.path.startsWith(`${PUBLIC}/times?`)).length).toBeGreaterThan(1);
  });

  it("says when a page is not available", async () => {
    renderApp(`/b/${WS}/${KEY}`, visitor({ page: { status: 404, body: { detail: "Not Found" } } }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This booking page is not available.");
  });
});

function manage(onCancel?: () => Reply, view: Reply = { status: 200, body: VIEW }): Handler {
  return (method, path) => {
    if (method === "POST" && path === `${BOOKINGS}/view`) return view;
    if (method === "POST" && path === `${BOOKINGS}/cancel`) return onCancel?.();
    return undefined;
  };
}

describe("the visitor's booking link", () => {
  it("shows the booking and cancels it with the token in the body", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/b/${WS}/manage#${TOKEN}`,
      manage(() => ({
        status: 200,
        body: { ...VIEW, cancelled: true, cancelled_by_visitor: true, can_cancel: false },
      })),
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Intro call" })).toBeInTheDocument();
    expect(screen.getByText(/meet\.example\.test/)).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Cancel booking" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel this booking?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel booking" }));
    expect(await screen.findByText("You cancelled this booking.")).toBeInTheDocument();
    expect(sent.find((r) => r.path === `${BOOKINGS}/view`)?.body).toEqual({ token: TOKEN });
    expect(sent.find((r) => r.path === `${BOOKINGS}/cancel`)?.body).toEqual({ token: TOKEN });
    expect(sent.every((r) => !r.path.includes(TOKEN))).toBe(true);
  });

  it("asks for the full link when the token is missing", async () => {
    const { sent } = renderApp(`/b/${WS}/manage`, manage());
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is incomplete.");
    expect(sent).toHaveLength(0);
  });

  it("says when the booking cannot be found", async () => {
    renderApp(`/b/${WS}/manage#${TOKEN}`, manage(undefined, { status: 404, body: { detail: "Not Found" } }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This booking could not be found.");
  });
});
