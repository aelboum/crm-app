import { screen } from "@testing-library/react";
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
    expect(router.state.location.pathname).toBe("/w/11111111-2222-4333-8444-555555555555");
    expect(await accessibilityViolations()).toEqual([]);
  });
});
