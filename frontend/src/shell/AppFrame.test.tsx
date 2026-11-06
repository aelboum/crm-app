import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

const WS = "11111111-2222-4333-8444-555555555555";

const signedIn: Handler = (method, path) => {
  if (method !== "GET") return undefined;
  if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
  if (path === `/v1/workspaces/${WS}`) {
    return {
      status: 200,
      body: { id: WS, name: "Acme Studio", status: "active" },
    };
  }
  if (path === `/v1/workspaces/${WS}/access`) {
    return {
      status: 200,
      body: {
        membership_id: "m",
        roles: ["Owner"],
        actions: { read_members: true },
      },
    };
  }
  if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
    return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
  }
  if (path === `/v1/workspaces/${WS}/me/notifications`) {
    return {
      status: 200,
      body: { items: [], next_cursor: null, unread: 0, unread_capped: false },
    };
  }
  return undefined;
};

const ACTOR = "aaaaaaaa-1111-4222-8333-444444444444";
const TASK = "bbbbbbbb-1111-4222-8333-444444444444";
const NOTIFIED = {
  items: [
    {
      id: "n1",
      kind: "task_assigned",
      subject_type: "task",
      subject_id: TASK,
      subject_label: "Call Ada back",
      actor_user_id: ACTOR,
      created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      read_at: null,
    },
    {
      id: "n2",
      kind: "booking_received",
      subject_type: "appointment",
      subject_id: "cccccccc-1111-4222-8333-444444444444",
      subject_label: null,
      actor_user_id: null,
      created_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      read_at: new Date().toISOString(),
    },
  ],
  next_cursor: null,
  unread: 1,
  unread_capped: false,
};

const notified: Handler = (method, path, body) => {
  if (path === `/v1/workspaces/${WS}/me/notifications`) {
    return { status: 200, body: NOTIFIED };
  }
  if (method === "POST" && path === `/v1/workspaces/${WS}/me/notifications/n1/read`) {
    return { status: 204 };
  }
  if (method === "POST" && path === `/v1/workspaces/${WS}/me/notifications/read-all`) {
    return { status: 200, body: { marked: 1 } };
  }
  return signedIn(method, path, body);
};

describe("app frame", () => {
  it("shows the design's navigation, marking every module that is not built", async () => {
    renderApp(`/w/${WS}/reviews`, signedIn);
    const nav = await screen.findByRole("navigation", { name: "Workspace" });
    for (const group of ["CRM", "Scheduling", "Marketing", "AI", "Insights"]) {
      expect(within(nav).getByRole("button", { name: group })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    }
    const reviews = within(nav).getByRole("link", { name: /Reviews/ });
    expect(reviews).toHaveAttribute("aria-current", "page");
    expect(reviews).toHaveTextContent("soon");
    // Campaigns are built (slice 7C).
    expect(
      within(nav).getByRole("link", { name: "Campaigns" }),
    ).not.toHaveTextContent("soon");
    // Contacts, Companies (slice 3A), Opportunities (4B), Tasks (4C) and
    // Calendar (5A) are built, so they carry no marker.
    expect(
      within(nav).getByRole("link", { name: "Calendar" }),
    ).not.toHaveTextContent("soon");
    expect(
      within(nav).getByRole("link", { name: "Opportunities" }),
    ).not.toHaveTextContent("soon");
    expect(
      within(nav).getByRole("link", { name: "Tasks" }),
    ).not.toHaveTextContent("soon");
    expect(
      within(nav).getByRole("link", { name: "Contacts" }),
    ).not.toHaveTextContent("soon");
    expect(
      within(nav).getByRole("link", { name: "Companies" }),
    ).not.toHaveTextContent("soon");
    expect(
      within(nav).getByRole("link", { name: "Settings" }),
    ).not.toHaveTextContent("soon");
  });

  it("opens the design's placeholder page for a module that is not built", async () => {
    renderApp(`/w/${WS}/reviews`, signedIn);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Reviews" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("collapses and expands the sidebar and its groups", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    const collapse = await screen.findByRole("button", {
      name: "Collapse sidebar",
    });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    await user.click(collapse);
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    const crm = screen.getByRole("button", { name: "CRM" });
    await user.click(crm);
    expect(crm).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: /Companies/ })).toBeNull();
  });

  it("opens a palette that navigates to pages and shows no record it was not given", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(
      await screen.findByRole("button", { name: /Search or jump to/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Search and go to" });
    const input = within(dialog).getByRole("searchbox", {
      name: "Search contacts and deals, or jump to a page…",
    });
    expect(input).toHaveFocus();
    await user.type(input, "zzqq");
    expect(
      await within(dialog).findByText("Nothing matches “zzqq”"),
    ).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "my prof");
    await user.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ section: "profile" });
    });
    expect(screen.queryByRole("dialog", { name: "Search and go to" })).toBeNull();
  });

  it("searches contacts and deals with the server's search and opens one", async () => {
    const user = userEvent.setup();
    const SAM = "d0000000-0000-4000-8000-000000000001";
    const DEAL = "f0000000-0000-4000-8000-000000000001";
    const withRecords: Handler = (method, path, body) => {
      const base = `/v1/workspaces/${WS}`;
      if (method === "GET" && path.startsWith(`${base}/contacts?`)) {
        return {
          status: 200,
          body: {
            items: [
              { id: SAM, first_name: "Sam", last_name: "Jansen", email: "sam@acme.example", company: null },
            ],
            next_cursor: null,
            total: 1,
            total_capped: false,
          },
        };
      }
      if (method === "GET" && path.startsWith(`${base}/opportunities?`)) {
        return {
          status: 200,
          body: {
            items: [
              { id: DEAL, title: "Website redesign", contact: { id: SAM, name: "Sam Jansen", archived: false }, company: null },
            ],
            next_cursor: null,
            total: 1,
            total_capped: false,
          },
        };
      }
      return signedIn(method, path, body);
    };
    const { sent, router } = renderApp(`/w/${WS}/settings`, withRecords);
    await user.keyboard("{Control>}k{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "Search and go to" });
    await user.type(within(dialog).getByRole("searchbox"), "sam");
    const contact = await within(dialog).findByRole("menuitem", { name: /sam@acme.example/ });
    expect(contact).toHaveTextContent("sam@acme.example");
    expect(
      within(dialog).getByRole("menuitem", { name: /Website redesign/ }),
    ).toBeInTheDocument();
    const searches = sent.filter((r) => r.method === "GET" && r.path.includes("q=sam"));
    expect(searches.map((r) => r.path.split("?")[0]).sort()).toEqual([
      `/v1/workspaces/${WS}/contacts`,
      `/v1/workspaces/${WS}/opportunities`,
    ]);
    // One character does not search.
    expect(sent.some((r) => r.path.includes("q=s&") || r.path.endsWith("q=s"))).toBe(false);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("menuitem", { name: /Website redesign/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/opportunities`);
    });
    expect(router.state.location.search).toEqual({ record: DEAL });
  });

  it("toggles the palette with Ctrl+K and closes it with Escape", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await screen.findByRole("heading", { name: "Team & roles" });
    await user.keyboard("{Control>}k{/Control}");
    expect(
      await screen.findByRole("dialog", { name: "Search and go to" }),
    ).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Search and go to" })).toBeNull();
    });
  });

  it("lists the design's create actions, none clickable without the rights", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: "New" }));
    const menu = await screen.findByRole("menu", { name: "New" });
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "Contact",
      "Opportunity",
      "Appointment",
      "Conversation",
      "Task",
    ]);
    for (const item of items)
      expect(item).toHaveAttribute("aria-disabled", "true");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it.each([
    ["Appointment", "create_appointment", "calendar", "appointment"],
    ["Conversation", "reply_conversations", "inbox", "conversation"],
  ])(
    "starts a new %s on its page for a member who may",
    async (label, action, section, create) => {
      const user = userEvent.setup();
      const may: Handler = (method, path, body) =>
        method === "GET" && path === `/v1/workspaces/${WS}/access`
          ? {
              status: 200,
              body: {
                membership_id: "m",
                roles: ["Member"],
                actions: { read_members: true, [action]: true },
              },
            }
          : signedIn(method, path, body);
      const { router } = renderApp(`/w/${WS}/settings`, may);
      await user.click(await screen.findByRole("button", { name: "New" }));
      const menu = await screen.findByRole("menu", { name: "New" });
      const item = within(menu).getByRole("menuitem", { name: label });
      expect(item).not.toHaveAttribute("aria-disabled");
      await user.click(item);
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(`/w/${WS}/${section}`);
      });
      expect(router.state.location.search).toEqual({ create });
    },
  );

  it("lets a member who may create contacts start one from the New menu", async () => {
    const user = userEvent.setup();
    const canCreate: Handler = (method, path, body) =>
      method === "GET" && path === `/v1/workspaces/${WS}/access`
        ? {
            status: 200,
            body: {
              membership_id: "m",
              roles: ["Member"],
              actions: { read_members: true, create_contact: true },
            },
          }
        : signedIn(method, path, body);
    renderApp(`/w/${WS}/settings`, canCreate);
    await user.click(await screen.findByRole("button", { name: "New" }));
    const menu = await screen.findByRole("menu", { name: "New" });
    const contact = within(menu).getByRole("menuitem", { name: "Contact" });
    expect(contact).not.toHaveAttribute("aria-disabled");
    expect(
      within(menu).getByRole("menuitem", { name: /Opportunity/ }),
    ).toHaveAttribute("aria-disabled", "true");
    await user.click(contact);
    expect(
      await screen.findByRole("dialog", { name: "New contact" }),
    ).toBeInTheDocument();
    // The modal hides the page beneath it from assistive technology.
    expect(
      screen.getByRole("heading", { level: 1, name: /Contacts/, hidden: true }),
    ).toBeInTheDocument();
  });

  it("switches to another of the caller's workspaces from the workspace menu", async () => {
    const user = userEvent.setup();
    const OTHER = "66666666-2222-4333-8444-555555555555";
    const withDirectory: Handler = (method, path, body) =>
      path === "/v1/workspaces"
        ? {
            status: 200,
            body: {
              items: [
                { id: WS, name: "Acme Studio" },
                { id: OTHER, name: "Beta Ltd" },
              ],
            },
          }
        : signedIn(method, path, body);
    const { router } = renderApp(`/w/${WS}/settings`, withDirectory);
    await screen.findByText("Acme Studio", { selector: ".ws-name" });
    await user.click(screen.getByRole("button", { name: /Client workspace/ }));
    // The menu is named by its trigger (the current workspace).
    const menu = await screen.findByRole("menu", { name: /Acme Studio/ });
    await user.click(
      await within(menu).findByRole("menuitem", { name: /Beta Ltd/ }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toMatch(
        new RegExp(`^/w/${OTHER}`),
      );
    });
  });

  it("shows an empty notifications panel when nothing happened to the member", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(
      await screen.findByRole("button", { name: "Notifications" }),
    );
    expect(
      await screen.findByText(/^No notifications yet\./),
    ).toBeInTheDocument();
  });

  it("shows the member's own notifications with an unread dot and opens one", async () => {
    const user = userEvent.setup();
    const { sent, router } = renderApp(`/w/${WS}/settings`, notified);
    const bell = await screen.findByRole("button", {
      name: "Notifications, 1 unread",
    });
    await user.click(bell);
    const list = await screen.findByRole("list", { name: "Notifications" });
    const buttons = within(list).getAllByRole("button");
    expect(buttons).toHaveLength(2);
    const [task, booking] = buttons as [HTMLElement, HTMLElement];
    expect(task).toHaveTextContent(
      `Member ${ACTOR.slice(0, 8)} assigned you a task (unread)`,
    );
    expect(task).toHaveTextContent("Call Ada back");
    expect(task).toHaveTextContent("5 minutes ago");
    // A visitor's booking, its appointment since deleted.
    expect(booking).toHaveTextContent("New booking on your booking page");
    expect(booking).toHaveTextContent("No longer available");
    expect(booking).not.toHaveTextContent("unread");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(task);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/tasks`);
    });
    expect(router.state.location.search).toEqual({ record: TASK });
    expect(sent).toContainEqual({
      method: "POST",
      path: `/v1/workspaces/${WS}/me/notifications/n1/read`,
      body: undefined,
    });
  });

  it("marks every notification read", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/settings`, notified);
    await user.click(
      await screen.findByRole("button", { name: "Notifications, 1 unread" }),
    );
    await user.click(await screen.findByRole("button", { name: "Mark all read" }));
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "POST",
        path: `/v1/workspaces/${WS}/me/notifications/read-all`,
        body: undefined,
      });
    });
  });

  it("says when notifications could not be loaded", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, (method, path, body) =>
      path === `/v1/workspaces/${WS}/me/notifications`
        ? { status: 500 }
        : signedIn(method, path, body),
    );
    await user.click(
      await screen.findByRole("button", { name: "Notifications" }),
    );
    // A server failure is retried twice first (App.tsx).
    expect(
      await screen.findByRole("alert", {}, { timeout: 8000 }),
    ).toBeInTheDocument();
  }, 15_000);

  it("answers an unknown section like an unknown workspace", async () => {
    renderApp(`/w/${WS}/nonsense`, signedIn);
    expect(
      await screen.findByText(
        "This workspace does not exist, or you are not a member of it.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the member's initials and name, and opens My profile from the account menu", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/contacts`, (method, path, body) => {
      if (method === "GET" && path === `/v1/workspaces/${WS}/me/profile`) {
        return { status: 200, body: { user_id: "u", display_name: "Ada Lovelace" } };
      }
      return signedIn(method, path, body);
    });
    const account = await screen.findByRole("button", { name: "Your account" });
    await waitFor(() => {
      expect(account).toHaveTextContent("AL");
    });
    await user.click(account);
    const menu = await screen.findByRole("menu", { name: "Your account" });
    expect(within(menu).getByText("Ada Lovelace")).toBeInTheDocument();
    const preferences = within(menu).getByRole("menuitem", { name: "Profile & preferences" });
    expect(preferences).not.toHaveAttribute("aria-disabled");
    await user.click(preferences);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
    expect(router.state.location.search).toEqual({ section: "profile" });
  });

  it("shows My profile with the real role, a display name that saves and the device's time zone", async () => {
    const user = userEvent.setup();
    const profile = `/v1/workspaces/${WS}/me/profile`;
    const { router, sent } = renderApp(`/w/${WS}/settings`, (method, path, body) => {
      if (path === `/v1/workspaces/${WS}/settings` && method === "GET") {
        // A zone no test machine uses, so the "differs" warning shows.
        return { status: 200, body: { time_zone: "Pacific/Kiritimati" } };
      }
      if (path === profile && method === "GET") {
        return { status: 200, body: { user_id: "u", display_name: null } };
      }
      if (path === profile && method === "PUT") {
        const name = (body as { display_name: string | null }).display_name;
        return { status: 200, body: { user_id: "u", display_name: name } };
      }
      return signedIn(method, path, body);
    });
    await user.click(await screen.findByRole("button", { name: "My profile" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "My profile" }),
    ).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ section: "profile" });
    expect(screen.getByText("Owner · Acme Studio")).toBeInTheDocument();
    // Decision M-P1: the display name is stored for this workspace.
    const name = screen.getByLabelText("Display name");
    await waitFor(() => {
      expect(name).toBeEnabled();
    });
    expect(name).toHaveAccessibleDescription(/Shown to the members of this workspace/);
    expect(screen.getByRole("button", { name: "Save name" })).toBeDisabled();
    await user.type(name, "  Anna de Vries ");
    await user.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByText("Display name saved")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "PUT")?.body).toEqual({
      display_name: "  Anna de Vries ",
    });
    // Decision M-P2: times use the device's zone; no picker that cannot save.
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone.replaceAll("_", " ");
    expect(screen.queryByRole("combobox", { name: "Time zone" })).not.toBeInTheDocument();
    expect(screen.getByText(`${zone} (this device)`)).toBeInTheDocument();
    expect(
      await screen.findByText(/The workspace's business time zone is Pacific\/Kiritimati/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Manage/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "My profile" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("on a phone, moves to the chosen settings section's heading", async () => {
    // The menu sits above the section below 760 px (styles.css).
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: "My profile" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "My profile" }),
    ).toHaveFocus();
  });

  it("on a wide screen, keeps focus on the settings menu item", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    const item = await screen.findByRole("button", { name: "My profile" });
    await user.click(item);
    await screen.findByRole("heading", { level: 1, name: "My profile" });
    expect(item).toHaveFocus();
  });

  it("opens My profile directly from its link", async () => {
    renderApp(`/w/${WS}/settings?section=profile`, signedIn);
    expect(
      await screen.findByRole("heading", { level: 1, name: "My profile" }),
    ).toBeInTheDocument();
  });

  it("renders the settings page with the role matrix and passes an accessibility scan", async () => {
    renderApp(`/w/${WS}/settings`, signedIn);
    expect(
      await screen.findByRole("heading", { name: "Role permissions" }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Capability", "Owner", "Admin", "Member", "Read-only"]);
    expect(await screen.findByText("No members to show.")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });
});
