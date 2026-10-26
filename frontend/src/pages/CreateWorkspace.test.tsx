import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";

import { rememberInvitation } from "../api/pendingInvitation";
import { signInNavigation } from "../api/signInRedirect";
import { normalizeWorkspaceName, workspaceNameProblem } from "../api/signups";
import { accessibilityViolations, type Handler, renderApp } from "../test/render";
import { POLL_DELAYS_MS } from "./CreateWorkspace";

/*
 * Stage D (decision S-1; SIGNUP-PLAN.md §4): the start page's workspace-name
 * step against the real `/v1/signups` contract, including SaaS-OS's
 * plain-text refusal codes and Retry-After.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const OTHER = "99999999-2222-4333-8444-555555555555";
const SIGNUP = "aaaaaaaa-2222-4333-8444-555555555555";

const signup = (state: string, workspace: string | null = null, error: string | null = null) => ({
  id: SIGNUP,
  state,
  workspace_id: workspace,
  created_at: "2026-10-26T10:00:00Z",
  error_code: error,
});

interface Reply {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
}

interface Options {
  status?: Reply;
  workspaces?: { id: string; name: string }[];
  current?: () => Reply | undefined;
  post?: (body: unknown) => Reply;
}

/** A signed-in person; every signup route answers as `options` says. */
function server(options: Options): Handler {
  // Like the real API, a completed signup's workspace joins the list.
  let workspaces = options.workspaces ?? [];
  const seen = (reply: Reply | undefined) => {
    const done = reply?.body as { state?: string; workspace_id?: string } | undefined;
    if (done?.state === "complete" && done.workspace_id && !workspaces.some((w) => w.id === done.workspace_id)) {
      workspaces = [...workspaces, { id: done.workspace_id, name: "Acme" }];
    }
    return reply;
  };
  return (method, path, body) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u" } };
    if (path === "/v1/workspaces") return { status: 200, body: { items: workspaces } };
    if (path === "/v1/signups/status") return options.status ?? { status: 200, body: { enabled: true } };
    if (path === "/v1/signups/current") {
      return seen(options.current?.()) ?? { status: 404, body: { detail: "Not Found" } };
    }
    if (method === "POST" && path === "/v1/signups" && options.post) return seen(options.post(body));
    return undefined;
  };
}

const keysSent = (sent: ReturnType<typeof renderApp>["headersSent"]) =>
  sent.filter((r) => r.method === "POST" && r.path === "/v1/signups").map((r) => r.headers["idempotency-key"]);

async function fill(name: string) {
  const user = userEvent.setup();
  const field = await screen.findByRole("textbox", { name: "Workspace name" });
  await user.clear(field);
  if (name) await user.type(field, name);
  await user.click(screen.getByRole("button", { name: "Create workspace" }));
  return user;
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("when the workspace-name step is offered", () => {
  it("shows it at once to a signed-in person with no workspace, accessibly", async () => {
    renderApp("/", server({}));
    expect(await screen.findByRole("heading", { name: "Create a workspace" })).toBeVisible();
    expect(await screen.findByRole("textbox", { name: "Workspace name" })).toBeVisible();
    expect(screen.getByText(/Create one below, or open an invitation link/)).toBeVisible();
    // No credentials are ever asked for here.
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("is not offered while signup is off, and nothing is asked of the signup routes", async () => {
    const { sent } = renderApp("/", server({ status: { status: 200, body: { enabled: false } } }));
    expect(await screen.findByText(/You are not a member of any workspace yet/)).toBeVisible();
    await waitFor(() => {
      expect(sent.some((r) => r.path === "/v1/signups/status")).toBe(true);
    });
    expect(screen.queryByRole("heading", { name: "Create a workspace" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Create workspace" })).toBeNull();
    expect(sent.some((r) => r.path === "/v1/signups/current" || r.method === "POST")).toBe(false);
  });

  it("is still offered when the status check fails, and the backend's 404 then says it is unavailable", async () => {
    renderApp(
      "/",
      server({
        status: { status: 503, body: { detail: "Unavailable" } },
        post: () => ({ status: 404, body: { detail: "Not Found" } }),
      }),
    );
    await fill("Acme");
    expect(await screen.findByText(/Creating workspaces is not available right now/)).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Workspace name" })).toBeNull();
  });

  it("sits behind Create workspace for someone who already has workspaces, and can be closed", async () => {
    const user = userEvent.setup();
    renderApp("/", server({ workspaces: [{ id: OTHER, name: "Existing" }] }));
    expect(await screen.findByRole("link", { name: /Existing/ })).toBeVisible();
    await user.click(await screen.findByRole("button", { name: "Create workspace" }));
    expect(await screen.findByRole("textbox", { name: "Workspace name" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox", { name: "Workspace name" })).toBeNull();
    // The workspace list and its links are unchanged.
    expect(screen.getByRole("link", { name: /Existing/ })).toBeVisible();
  });

  it("gives way to an invitation waiting in this tab", async () => {
    rememberInvitation({ workspaceId: OTHER, token: "t" });
    const { sent } = renderApp("/", server({}));
    expect(await screen.findByText("You have an invitation waiting.")).toBeVisible();
    expect(await screen.findByRole("heading", { name: "Your workspaces" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Create a workspace" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Create workspace" })).toBeNull();
    // Only the public flag may be read (by the screen shown before the session is known).
    expect(sent.some((r) => r.path === "/v1/signups/current" || r.path === "/v1/signups")).toBe(false);
  });

  it("points an invited person to their invitation link", async () => {
    renderApp("/", server({}));
    expect(await screen.findByText(/Open the invitation link from your email instead/)).toBeVisible();
  });
});

describe("the workspace name", () => {
  it("is checked as the backend checks it", () => {
    expect(normalizeWorkspaceName("  Acme \t  Sales  ")).toBe("Acme Sales");
    expect(normalizeWorkspaceName("Café")).toBe("Café");
    expect(workspaceNameProblem("   ")).toBe("empty");
    expect(workspaceNameProblem("x".repeat(100))).toBeNull();
    expect(workspaceNameProblem("x".repeat(101))).toBe("long");
    expect(workspaceNameProblem("😀".repeat(100))).toBeNull();
    expect(workspaceNameProblem("Acme​")).toBe("character");
    expect(workspaceNameProblem("Acme\u0007")).toBe("character");
  });

  it("is refused here when empty, without asking the server", async () => {
    const post = vi.fn(() => ({ status: 201, body: signup("complete", WS) }));
    renderApp("/", server({ post }));
    await fill("");
    expect(await screen.findByText("Enter a name for the workspace.")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Workspace name" })).toHaveAttribute("aria-invalid", "true");
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the server's invalid_workspace_name refusal (400) on the field", async () => {
    renderApp("/", server({ post: () => ({ status: 400, body: { detail: "invalid_workspace_name" } }) }));
    await fill("Acme");
    expect(await screen.findByText(/This name cannot be used/)).toBeVisible();
  });
});

describe("provisioning", () => {
  it("opens the new workspace's settings only once the signup is complete (201)", async () => {
    const { router, sent, headersSent } = renderApp(
      "/",
      server({ post: () => ({ status: 201, body: signup("complete", WS) }) }),
    );
    await fill("  Acme   Sales ");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
    const posted = sent.filter((r) => r.method === "POST" && r.path === "/v1/signups");
    expect(posted.map((r) => r.body)).toEqual([{ workspace_name: "Acme Sales" }]);
    expect(keysSent(headersSent)).toHaveLength(1);
    expect(keysSent(headersSent)[0]).toMatch(/^[0-9a-f-]{36}$/);
    // The workspace list was asked again after completion.
    expect(sent.filter((r) => r.path === "/v1/workspaces").length).toBeGreaterThan(1);
    expect(sessionStorage.getItem("crm.signupAttempt")).toBeNull();
  });

  it("follows a signup that is still provisioning (202) until it completes", async () => {
    let checks = 0;
    let posted = false;
    const { router } = renderApp(
      "/",
      server({
        post: () => {
          posted = true;
          return { status: 202, body: signup("provisioning") };
        },
        current: () => {
          if (!posted) return undefined;
          checks += 1;
          return { status: 200, body: checks < 2 ? signup("provisioning") : signup("complete", WS) };
        },
      }),
    );
    await fill("Acme");
    expect(await screen.findByText("Setting up your workspace…")).toBeVisible();
    // Not reported as done before the backend says so.
    expect(router.state.location.pathname).toBe("/");
    await waitFor(
      () => {
        expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
      },
      { timeout: 5000 },
    );
  });

  it("treats a replay answer (200) by its state", async () => {
    const { router } = renderApp("/", server({ post: () => ({ status: 200, body: signup("complete", WS) }) }));
    await fill("Acme");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
  });

  it("resumes an unfinished signup on arrival", async () => {
    let checks = 0;
    const { router } = renderApp(
      "/",
      server({
        current: () => {
          checks += 1;
          return { status: 200, body: checks < 2 ? signup("started") : signup("complete", WS) };
        },
      }),
    );
    expect(await screen.findByText("Setting up your workspace…")).toBeVisible();
    await waitFor(
      () => {
        expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
      },
      { timeout: 5000 },
    );
  });

  describe("when the checks run out", () => {
    let saved: number[] = [];
    beforeEach(() => {
      saved = POLL_DELAYS_MS.splice(0, POLL_DELAYS_MS.length, 10, 10);
    });
    afterEach(() => {
      POLL_DELAYS_MS.splice(0, POLL_DELAYS_MS.length, ...saved);
    });

    it("says it continues in the background, and Check again repeats the same attempt", async () => {
      let completed = false;
      let posted = false;
      const { router, headersSent } = renderApp(
        "/",
        server({
          post: () => {
            posted = true;
            return { status: 202, body: completed ? signup("complete", WS) : signup("provisioning") };
          },
          current: () => (posted ? { status: 200, body: signup("provisioning") } : undefined),
        }),
      );
      const user = await fill("Acme");
      expect(await screen.findByText(/taking longer than usual/)).toBeVisible();
      expect(screen.getByRole("heading", { name: "Create a workspace" })).toHaveFocus();
      completed = true;
      await user.click(screen.getByRole("button", { name: "Check again" }));
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
      });
      const sentKeys = keysSent(headersSent);
      expect(sentKeys).toHaveLength(2);
      expect(sentKeys[1]).toBe(sentKeys[0]);
    });
  });

  it("reports a failed signup and starts a new attempt with a new key", async () => {
    let failed = true;
    const { router, headersSent } = renderApp(
      "/",
      server({
        post: () => ({
          status: 201,
          body: failed ? signup("failed", null, "workspace_claim_failed") : signup("complete", WS),
        }),
      }),
    );
    const user = await fill("Acme");
    expect(await screen.findByText(/could not be set up/)).toBeVisible();
    failed = false;
    await user.click(screen.getByRole("button", { name: "Start again" }));
    await user.click(await screen.findByRole("button", { name: "Create workspace" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
    const sentKeys = keysSent(headersSent);
    expect(sentKeys).toHaveLength(2);
    expect(sentKeys[1]).not.toBe(sentKeys[0]);
  });

  it("reports an expired attempt this tab was making", async () => {
    sessionStorage.setItem("crm.signupAttempt", JSON.stringify({ key: "k", name: "Acme" }));
    renderApp("/", server({ current: () => ({ status: 200, body: signup("expired", null, "expired") }) }));
    expect(await screen.findByText(/expired before it was finished/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Start again" })).toBeVisible();
  });

  it("forgets a kept attempt whose signup already completed, so the next one is new", async () => {
    sessionStorage.setItem("crm.signupAttempt", JSON.stringify({ key: "old-key", name: "Acme" }));
    const { headersSent } = renderApp(
      "/",
      server({
        current: () => ({ status: 200, body: signup("complete", OTHER) }),
        post: () => ({ status: 201, body: signup("complete", WS) }),
      }),
    );
    expect(await screen.findByRole("textbox", { name: "Workspace name" })).toHaveValue("");
    await fill("Acme");
    await waitFor(() => {
      expect(keysSent(headersSent)).toHaveLength(1);
    });
    expect(keysSent(headersSent)[0]).not.toBe("old-key");
  });

  it("stays open while provisioning even when the refreshed list already shows the workspace", async () => {
    // The first-signup case: the list goes from empty to one workspace.
    let posted = false;
    const { router } = renderApp(
      "/",
      server({
        post: () => {
          posted = true;
          return { status: 202, body: signup("provisioning") };
        },
        current: () => (posted ? { status: 200, body: signup("complete", WS) } : undefined),
      }),
    );
    await fill("Acme");
    await waitFor(
      () => {
        expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
      },
      { timeout: 5000 },
    );
  });

  it("does not bring up an old failed signup from another visit", async () => {
    renderApp("/", server({ current: () => ({ status: 200, body: signup("failed") }) }));
    expect(await screen.findByRole("textbox", { name: "Workspace name" })).toBeVisible();
    expect(screen.queryByText(/could not be set up/)).toBeNull();
  });
});

describe("refusals and failures", () => {
  it("asks for a verified email when the person has none (403 from current)", async () => {
    renderApp("/", server({ current: () => ({ status: 403, body: { detail: "Not authorized." } }) }));
    expect(await screen.findByText(/Verify your email address/)).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Workspace name" })).toBeNull();
  });

  it("names the verified-email requirement after a 403 only when current confirms it", async () => {
    let afterPost = false;
    renderApp(
      "/",
      server({
        post: () => {
          afterPost = true;
          return { status: 403, body: { detail: "Not authorized." } };
        },
        current: () => (afterPost ? { status: 403, body: { detail: "Not authorized." } } : undefined),
      }),
    );
    await fill("Acme");
    expect(await screen.findByText(/Verify your email address/)).toBeVisible();
  });

  it("does not call another 403 a missing verified email", async () => {
    renderApp("/", server({ post: () => ({ status: 403, body: { detail: "Not authorized." } }) }));
    await fill("Acme");
    expect(await screen.findByText(/not allowed to create a workspace from this page/)).toBeVisible();
    expect(screen.queryByText(/Verify your email address/)).toBeNull();
  });

  it("explains the workspace limit (409 workspace_limit_reached)", async () => {
    renderApp("/", server({ post: () => ({ status: 409, body: { detail: "workspace_limit_reached" } }) }));
    await fill("Acme");
    expect(await screen.findByText(/reached the number of workspaces you can create/)).toBeVisible();
  });

  it("starts a new attempt after a reused key (409 idempotency_key_reused)", async () => {
    let first = true;
    const { headersSent } = renderApp(
      "/",
      server({
        post: () => {
          if (first) {
            first = false;
            return { status: 409, body: { detail: "idempotency_key_reused" } };
          }
          return { status: 201, body: signup("complete", WS) };
        },
      }),
    );
    const user = await fill("Acme");
    expect(await screen.findByText(/could not be repeated/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => {
      expect(keysSent(headersSent)).toHaveLength(2);
    });
    const sentKeys = keysSent(headersSent);
    expect(sentKeys[1]).not.toBe(sentKeys[0]);
  });

  it("waits out Retry-After on 429, then allows the same attempt again", async () => {
    let first = true;
    const { headersSent, router } = renderApp(
      "/",
      server({
        post: () => {
          if (first) {
            first = false;
            return { status: 429, body: { detail: "Rate limit exceeded." }, headers: { "Retry-After": "1" } };
          }
          return { status: 201, body: signup("complete", WS) };
        },
      }),
    );
    const user = await fill("Acme");
    expect(await screen.findByText("Too many requests right now. Try again in 1 second.")).toBeVisible();
    const button = screen.getByRole("button", { name: "Create workspace" });
    expect(button).toBeDisabled();
    await waitFor(
      () => {
        expect(button).toBeEnabled();
      },
      { timeout: 3000 },
    );
    await user.click(button);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
    const sentKeys = keysSent(headersSent);
    expect(sentKeys).toHaveLength(2);
    expect(sentKeys[1]).toBe(sentKeys[0]);
  });

  it("states a long wait in minutes on 503", async () => {
    renderApp(
      "/",
      server({
        post: () => ({ status: 503, body: { detail: "Service unavailable." }, headers: { "Retry-After": "3600" } }),
      }),
    );
    await fill("Acme");
    expect(await screen.findByText("Too many requests right now. Try again in 60 minutes.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create workspace" })).toBeDisabled();
  });

  it("retries the same attempt after a network failure", async () => {
    let offline = true;
    const { headersSent, router } = renderApp(
      "/",
      server({
        post: () => {
          if (offline) {
            offline = false;
            throw new TypeError("Failed to fetch");
          }
          return { status: 201, body: signup("complete", WS) };
        },
      }),
    );
    const user = await fill("Acme");
    expect(await screen.findByText(/could not reach LeadStack/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/settings`);
    });
    const sentKeys = keysSent(headersSent);
    expect(sentKeys).toHaveLength(2);
    expect(sentKeys[1]).toBe(sentKeys[0]);
  });

  it("keeps the attempt's key across a reload of the page", async () => {
    sessionStorage.setItem("crm.signupAttempt", JSON.stringify({ key: "kept-key", name: "Acme" }));
    const { headersSent } = renderApp("/", server({ post: () => ({ status: 201, body: signup("complete", WS) }) }));
    // The name of the unfinished attempt is filled in again.
    expect(await screen.findByRole("textbox", { name: "Workspace name" })).toHaveValue("Acme");
    await userEvent.setup().click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => {
      expect(keysSent(headersSent)).toEqual(["kept-key"]);
    });
  });
});

describe("the sign-in screen's Create account entry", () => {
  const signedOut =
    (status: Reply): Handler =>
    (_, path) => {
      if (path === "/v1/signups/status") return status;
      return { status: 401, body: { detail: "Not authenticated" } };
    };

  beforeEach(() => {
    // Stay on the screen instead of leaving for the provider.
    const leave = vi.spyOn(signInNavigation, "leave").mockImplementation(() => undefined);
    sessionStorage.setItem("crm.signedOut", "1");
    onTestFinished(() => {
      leave.mockRestore();
    });
  });

  it("is offered when signup is on, and leads to the provider's sign-in page", async () => {
    renderApp("/", signedOut({ status: 200, body: { enabled: true } }));
    const link = await screen.findByRole("link", { name: "Create account" });
    expect(link).toHaveAttribute("href", "/auth/login");
    expect(screen.getByText(/Choose “Create one” on the sign-in page/)).toBeVisible();
    const aside = screen.getByRole("complementary", { name: "LeadStack" });
    expect(within(aside).queryByText(/There is no public sign-up/)).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("is not offered when signup is off, which the screen then says", async () => {
    renderApp("/", signedOut({ status: 200, body: { enabled: false } }));
    expect(await screen.findByText(/There is no public sign-up/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Create account" })).toBeNull();
  });

  it("claims neither when the status is unknown", async () => {
    const { sent } = renderApp("/", signedOut({ status: 500, body: { detail: "Error" } }));
    await screen.findByRole("link", { name: "Sign in" });
    await waitFor(() => {
      expect(sent.some((r) => r.path === "/v1/signups/status")).toBe(true);
    });
    expect(screen.queryByRole("link", { name: "Create account" })).toBeNull();
    expect(screen.queryByText(/There is no public sign-up/)).toBeNull();
  });
});
