import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

const WS = "11111111-2222-4333-8444-555555555555";

const signedIn: Handler = (method, path) => {
  if (method !== "GET") return undefined;
  if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
  if (path === `/v1/workspaces/${WS}`) {
    return { status: 200, body: { id: WS, name: "Acme Studio", status: "active" } };
  }
  if (path === `/v1/workspaces/${WS}/access`) {
    return {
      status: 200,
      body: { membership_id: "m", roles: ["Owner"], actions: { read_members: true } },
    };
  }
  if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
    return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
  }
  return undefined;
};

describe("app frame", () => {
  it("shows the design's navigation, marking every module that is not built", async () => {
    renderApp(`/w/${WS}/calendar`, signedIn);
    const nav = await screen.findByRole("navigation", { name: "Workspace" });
    for (const group of ["CRM", "Scheduling", "Marketing", "AI", "Insights"]) {
      expect(within(nav).getByRole("button", { name: group })).toHaveAttribute("aria-expanded", "true");
    }
    const calendar = within(nav).getByRole("link", { name: /Calendar/ });
    expect(calendar).toHaveAttribute("aria-current", "page");
    expect(calendar).toHaveTextContent("soon");
    // Contacts, Companies (slice 3A), Opportunities (4B) and Tasks (4C) are
    // built, so they carry no marker.
    expect(within(nav).getByRole("link", { name: "Opportunities" })).not.toHaveTextContent("soon");
    expect(within(nav).getByRole("link", { name: "Tasks" })).not.toHaveTextContent("soon");
    expect(within(nav).getByRole("link", { name: "Contacts" })).not.toHaveTextContent("soon");
    expect(within(nav).getByRole("link", { name: "Companies" })).not.toHaveTextContent("soon");
    expect(within(nav).getByRole("link", { name: "Settings" })).not.toHaveTextContent("soon");
  });

  it("opens the design's placeholder page for a module that is not built", async () => {
    renderApp(`/w/${WS}/calendar`, signedIn);
    expect(await screen.findByRole("heading", { level: 1, name: "Calendar" })).toBeInTheDocument();
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("collapses and expands the sidebar and its groups", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    const collapse = await screen.findByRole("button", { name: "Collapse sidebar" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    await user.click(collapse);
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    const crm = screen.getByRole("button", { name: "CRM" });
    await user.click(crm);
    expect(crm).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: /Companies/ })).toBeNull();
  });

  it("opens a page palette that navigates and never pretends to search records", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: /Jump to a page/ }));
    const dialog = await screen.findByRole("dialog", { name: "Go to a page" });
    expect(
      within(dialog).getByText("Searching contacts, deals and other records is not available yet."),
    ).toBeInTheDocument();
    const input = within(dialog).getByRole("searchbox", { name: "Jump to a page…" });
    expect(input).toHaveFocus();
    await user.type(input, "zzqq");
    expect(within(dialog).getByText("No pages match “zzqq”")).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "my prof");
    await user.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ section: "profile" });
    });
    expect(screen.queryByRole("dialog", { name: "Go to a page" })).toBeNull();
  });

  it("toggles the palette with Ctrl+K and closes it with Escape", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await screen.findByRole("heading", { name: "Team & roles" });
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Go to a page" })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Go to a page" })).toBeNull();
    });
  });

  it("lists the design's create actions as not available, none clickable", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: "New" }));
    const menu = await screen.findByRole("menu", { name: "New" });
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "ContactNot available yet",
      "OpportunityNot available yet",
      "AppointmentNot available yet",
      "ConversationNot available yet",
      "TaskNot available yet",
    ]);
    for (const item of items) expect(item).toHaveAttribute("aria-disabled", "true");
    expect(await accessibilityViolations()).toEqual([]);
  });

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
    expect(within(menu).getByRole("menuitem", { name: /Opportunity/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.click(contact);
    expect(await screen.findByRole("dialog", { name: "New contact" })).toBeInTheDocument();
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
    await user.click(await within(menu).findByRole("menuitem", { name: /Beta Ltd/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toMatch(new RegExp(`^/w/${OTHER}`));
    });
  });

  it("shows an empty notifications panel rather than invented notifications", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(await screen.findByText("No notifications yet.")).toBeInTheDocument();
  });

  it("answers an unknown section like an unknown workspace", async () => {
    renderApp(`/w/${WS}/nonsense`, signedIn);
    expect(
      await screen.findByText("This workspace does not exist, or you are not a member of it."),
    ).toBeInTheDocument();
  });

  it("shows My profile with the real role and no field that pretends to save", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/settings`, signedIn);
    await user.click(await screen.findByRole("button", { name: "My profile" }));
    expect(await screen.findByRole("heading", { level: 1, name: "My profile" })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ section: "profile" });
    expect(screen.getByText("Owner · Acme Studio")).toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toBeDisabled();
    expect(screen.getByLabelText("Time zone")).toBeDisabled();
    expect(screen.getByLabelText("Display name")).toHaveAccessibleDescription(
      /can't be saved yet/,
    );
    expect(screen.getByRole("button", { name: /Manage/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "My profile" })).toHaveAttribute("aria-current", "page");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("opens My profile directly from its link", async () => {
    renderApp(`/w/${WS}/settings?section=profile`, signedIn);
    expect(await screen.findByRole("heading", { level: 1, name: "My profile" })).toBeInTheDocument();
  });

  it("renders the settings page with the role matrix and passes an accessibility scan", async () => {
    renderApp(`/w/${WS}/settings`, signedIn);
    expect(await screen.findByRole("heading", { name: "Role permissions" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Capability",
      "Owner",
      "Admin",
      "Member",
      "Read-only",
    ]);
    expect(await screen.findByText("No members to show.")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });
});
