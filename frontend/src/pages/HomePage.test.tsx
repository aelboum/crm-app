import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, renderApp } from "../test/render";

describe("home", () => {
  it("offers sign-in to a visitor without a session", async () => {
    renderApp("/", () => ({ status: 401, body: { detail: "Not authenticated" } }));
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link).toHaveAttribute("href", "/auth/login");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("lists the caller's workspaces as links, by name", async () => {
    renderApp("/", (_, path) => {
      if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") {
        return {
          status: 200,
          body: {
            items: [
              { id: "11111111-2222-4333-8444-555555555555", name: "Acme BV" },
              { id: "66666666-2222-4333-8444-555555555555", name: "Beta Ltd" },
            ],
          },
        };
      }
      return undefined;
    });
    const list = await screen.findByRole("list");
    const links = await within(list).findAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Acme BV", "Beta Ltd"]);
    expect(links[0]).toHaveAttribute("href", "/app/w/11111111-2222-4333-8444-555555555555");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("says so when the caller belongs to no workspace", async () => {
    renderApp("/", (_, path) => {
      if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      return undefined;
    });
    expect(await screen.findByText(/not a member of any workspace yet/)).toBeInTheDocument();
  });

  it("opens a workspace by ID once the ID is well formed", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/", (_, path) =>
      path === "/auth/me" ? { status: 200, body: { user_id: "u" } } : undefined,
    );
    const field = await screen.findByLabelText(/Workspace ID/);
    const open = screen.getByRole("button", { name: "Open" });

    await user.type(field, "not-an-id");
    expect(open).toBeDisabled();
    await user.tab();
    expect(await screen.findByText(/Enter a workspace ID/)).toBeInTheDocument();

    await user.clear(field);
    await user.type(field, "11111111-2222-4333-8444-555555555555");
    await user.click(open);
    // The workspace opens on Settings › Team & roles, the one module that exists.
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/w/11111111-2222-4333-8444-555555555555/settings");
    });
    expect(await accessibilityViolations()).toEqual([]);
  });
});
