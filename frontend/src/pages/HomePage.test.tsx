import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, onTestFinished } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

const signedOut: Handler = () => ({ status: 401, body: { detail: "Not authenticated" } });

describe("sign-in screen", () => {
  it("offers the branded sign-in to a visitor without a session", async () => {
    renderApp("/", signedOut);
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in to LeadStack" })).toBeVisible();
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link).toHaveAttribute("href", "/auth/login");
    expect(within(screen.getByRole("complementary", { name: "LeadStack" })).getByText("LeadStack")).toBeVisible();
    // The application header and its sign-out belong to a session.
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("offers no sign-up, no other provider and no credential field (P2-C, ADR-0026)", async () => {
    renderApp("/", signedOut);
    await screen.findByRole("link", { name: "Sign in" });
    // The only other link is the skip link to the page's own content.
    expect(screen.getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["#main", "/auth/login"]);
    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(document.querySelector("input, form")).toBeNull();
    expect(screen.queryByText(/create (an |your )?account|sign up for|google|microsoft/i)).toBeNull();
    expect(screen.getByText(/Ask an Owner or Admin of your organisation to invite you/)).toBeVisible();
  });

  it("says it is leaving for the sign-in page and ignores a second click", async () => {
    const user = userEvent.setup();
    renderApp("/", signedOut);
    const link = await screen.findByRole("link", { name: "Sign in" });
    // jsdom does not navigate; record whether each click was let through,
    // after React's own handler (on the root) has seen it.
    const followed: boolean[] = [];
    const record = (event: MouseEvent) => {
      followed.push(!event.defaultPrevented);
      event.preventDefault();
    };
    document.addEventListener("click", record);
    onTestFinished(() => {
      document.removeEventListener("click", record);
    });
    await user.click(link);
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Opening the sign-in page…")).toHaveAttribute("role", "status");
    await user.click(link);
    expect(followed).toEqual([true, false]);

    // Back from the provider through the back/forward cache: usable again.
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    await waitFor(() => {
      expect(link).not.toHaveAttribute("aria-disabled");
    });
  });

  it("checks the session before offering sign-in", async () => {
    renderApp("/", signedOut);
    expect(await screen.findByText("Checking your session…")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeVisible();
  });

  it("still offers sign-in when the session check fails, with a retry", async () => {
    const user = userEvent.setup();
    let failing = true;
    renderApp("/", (_, path) => {
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      if (path !== "/auth/me") return undefined;
      return failing ? { status: 503, body: { detail: "Unavailable" } } : { status: 200, body: { user_id: "u" } };
    });
    // A server failure is retried twice before it is shown (App.tsx).
    const alert = await screen.findByRole("alert", {}, { timeout: 8000 });
    expect(alert).toHaveTextContent("We could not check whether you are signed in.");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/auth/login");
    expect(await accessibilityViolations()).toEqual([]);

    failing = false;
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Your workspaces" })).toBeVisible();
  }, 15000);

  it("signs out from the start page and asks for the provider's sign-out address", async () => {
    const user = userEvent.setup();
    let ended = false;
    const { sent } = renderApp("/", (method, path) => {
      if (method === "POST" && path === "/auth/logout") {
        ended = true;
        return { status: 204 };
      }
      if (path === "/auth/me") return ended ? { status: 401, body: {} } : { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      if (path === "/v1/sign-out-url") return { status: 200, body: { url: null } };
      return undefined;
    });
    expect(within(await screen.findByRole("banner")).getByText("LeadStack")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("link", { name: "Sign in" })).toBeVisible();
    expect(screen.queryByRole("banner")).toBeNull();
    await waitFor(() => {
      expect(sent.map((s) => `${s.method} ${s.path}`)).toContain("GET /v1/sign-out-url");
    });
    expect(sent.map((s) => `${s.method} ${s.path}`)).toContain("POST /auth/logout");
  });
});

describe("home", () => {

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
