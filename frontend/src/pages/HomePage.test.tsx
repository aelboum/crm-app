import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, type MockInstance, onTestFinished, vi } from "vitest";

import { markSignedOut, signInNavigation } from "../api/signInRedirect";
import { signOutNavigation } from "../api/signOut";
import { accessibilityViolations, type Handler, renderApp } from "../test/render";

const signedOut: Handler = () => ({ status: 401, body: { detail: "Not authenticated" } });

let leave: MockInstance<(url: string) => void>;
beforeEach(() => {
  sessionStorage.clear();
  leave = vi.spyOn(signInNavigation, "leave").mockImplementation(() => undefined);
  onTestFinished(() => {
    leave.mockRestore();
  });
});

describe("start page without a session (decision S-2)", () => {
  it("sends the visitor straight on to the sign-in page, once", async () => {
    renderApp("/", signedOut);
    await waitFor(() => {
      expect(leave).toHaveBeenCalledWith("/auth/login");
    });
    expect(leave).toHaveBeenCalledTimes(1);
    // The link stays usable while the browser leaves.
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/auth/login");
  });

  it("stays after a sign-out in this tab, and following the link clears that", async () => {
    const user = userEvent.setup();
    markSignedOut();
    renderApp("/", signedOut);
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(leave).not.toHaveBeenCalled();
    const stop = (event: MouseEvent) => {
      event.preventDefault();
    };
    document.addEventListener("click", stop);
    onTestFinished(() => {
      document.removeEventListener("click", stop);
    });
    await user.click(link);
    expect(sessionStorage.getItem("crm.signedOut")).toBeNull();
  });

  it("does not send the visitor on again within 10 seconds", async () => {
    sessionStorage.setItem("crm.signInRedirectAt", String(Date.now() - 2000));
    renderApp("/", signedOut);
    await screen.findByRole("link", { name: "Sign in" });
    expect(leave).not.toHaveBeenCalled();
  });

  it("does not leave when the session check fails", async () => {
    renderApp("/", (_, path) => (path === "/auth/me" ? { status: 503, body: { detail: "Unavailable" } } : undefined));
    await screen.findByRole("alert", {}, { timeout: 8000 });
    expect(leave).not.toHaveBeenCalled();
  }, 15000);

  it("never leaves a signed-in person, and a confirmed session clears the sign-out mark", async () => {
    markSignedOut();
    renderApp("/", (_, path) => {
      if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      return undefined;
    });
    expect(await screen.findByRole("heading", { name: "Your workspaces" })).toBeVisible();
    expect(leave).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("crm.signedOut")).toBeNull();
  });
});

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
    markSignedOut(); // the screen stays, as after a sign-out
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
    // Signed out on purpose: the start page must not sign in again by itself.
    expect(leave).not.toHaveBeenCalled();
  });

  it("ends the session, then hands the browser to the provider's sign-out, which returns to /auth/login (P2-G.1)", async () => {
    const user = userEvent.setup();
    const endSession =
      "http://localhost:8000/oidc/v1/end_session?client_id=c&post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Flogin";
    const go = vi.spyOn(signOutNavigation, "go").mockImplementation(() => undefined);
    onTestFinished(() => {
      go.mockRestore();
    });
    let ended = false;
    const { sent } = renderApp("/", (method, path) => {
      if (method === "POST" && path === "/auth/logout") {
        ended = true;
        return { status: 204 };
      }
      if (path === "/auth/me") return ended ? { status: 401, body: {} } : { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      if (path === "/v1/sign-out-url") return { status: 200, body: { url: endSession } };
      return undefined;
    });
    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(go).toHaveBeenCalledWith(endSession);
    });
    expect(go).toHaveBeenCalledTimes(1);
    // LeadStack's own session ended first, and nothing signed-in stays on screen.
    expect(ended).toBe(true);
    expect(sent.map((s) => `${s.method} ${s.path}`)).toContain("POST /auth/logout");
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Your workspaces" })).toBeNull();
    // The start page does not race the provider's sign-out with a sign-in.
    expect(leave).not.toHaveBeenCalled();
  });

  it("does not leave for the provider's sign-out when LeadStack's own sign-out fails", async () => {
    const user = userEvent.setup();
    const go = vi.spyOn(signOutNavigation, "go").mockImplementation(() => undefined);
    onTestFinished(() => {
      go.mockRestore();
    });
    renderApp("/", (method, path) => {
      if (method === "POST" && path === "/auth/logout") return { status: 503, body: { detail: "Unavailable" } };
      if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
      if (path === "/v1/workspaces") return { status: 200, body: { items: [] } };
      if (path === "/v1/sign-out-url") return { status: 200, body: { url: "http://localhost:8000/oidc/v1/end_session" } };
      return undefined;
    });
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Your workspaces" })).toBeVisible();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(go).not.toHaveBeenCalled();
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
