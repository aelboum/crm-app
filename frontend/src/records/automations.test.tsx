import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Automations (decision P8-A): the list with status and summary, what each
 * role is offered, building a draft from the design's shape (sources, a
 * condition, steps), activation with the version, refusals by code, and a
 * run's history opening its contact. Only the actions the engine runs are
 * offered. The server checks every definition again.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const AUTO = "a0000000-0000-4000-8000-000000000001";
const TAG = "b0000000-0000-4000-8000-000000000001";
const CONTACT = "c0000000-0000-4000-8000-000000000001";
const stamp = "2026-11-01T09:30:00+00:00";

const DEFINITION = {
  trigger: { type: "contact_created", sources: ["form"] },
  condition: null,
  yes: [{ type: "add_tag", tag_id: TAG }],
  no: [],
};

function automation(extra: Record<string, unknown> = {}) {
  return {
    id: AUTO,
    name: "Welcome form leads",
    status: "draft",
    trigger_type: "contact_created",
    definition: DEFINITION,
    active_version: null,
    created_at: stamp,
    updated_at: stamp,
    version: 2,
    ...extra,
  };
}

const RUNS = {
  items: [
    {
      id: "r1",
      contact_id: CONTACT,
      version: 1,
      branch: "yes",
      status: "completed",
      resume_at: null,
      attempts: 0,
      last_error: null,
      created_at: stamp,
      finished_at: stamp,
      steps: [
        {
          branch: "yes",
          position: 0,
          action: "add_tag",
          outcome: "done",
          detail: null,
          executed_at: stamp,
        },
      ],
    },
  ],
};

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  manage: boolean,
  options: {
    items?: unknown[];
    onWrite?: (method: string, path: string, body: unknown) => Reply;
  } = {},
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return options.onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: ["Owner"],
          actions: {
            read_automations: true,
            manage_automations: manage,
            read_members: true,
          },
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: {
          items: [{ user_id: ME, status: "active", roles: ["Owner"] }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      };
    }
    if (path === `${base}/tags`) {
      return {
        status: 200,
        body: { items: [{ id: TAG, name: "Hot lead", version: 1, usage: 0 }] },
      };
    }
    if (path === `${base}/automations`)
      return { status: 200, body: { items: options.items ?? [automation()] } };
    if (path === `${base}/automations/${AUTO}/runs`)
      return { status: 200, body: RUNS };
    return undefined;
  };
}

describe("automations", () => {
  it("lists automations with their status and what starts them", async () => {
    renderApp(`/w/${WS}/automations`, workspace(true));
    const card = await screen.findByRole("listitem", {
      name: "Welcome form leads",
    });
    expect(card).toHaveTextContent("Draft");
    expect(card).toHaveTextContent(
      "When a contact is created from Form · 1 step",
    );
    expect(
      within(card).getByRole("button", { name: "Activate" }),
    ).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("offers a member without the manage permission the list and runs only", async () => {
    renderApp(`/w/${WS}/automations`, workspace(false));
    const card = await screen.findByRole("listitem", {
      name: "Welcome form leads",
    });
    expect(screen.queryByRole("button", { name: "New automation" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Activate" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(
      within(card).getByRole("button", { name: "Show runs" }),
    ).toBeInTheDocument();
  });

  it("builds a draft from sources, a condition and steps", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/automations`,
      workspace(true, {
        items: [],
        onWrite: (method) =>
          method === "POST" ? { status: 201, body: automation() } : undefined,
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: "New automation" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "New automation",
    });
    await user.type(
      within(dialog).getByLabelText("Name"),
      "Welcome form leads",
    );
    await user.click(within(dialog).getByRole("checkbox", { name: "Form" }));
    await user.selectOptions(
      within(dialog).getByLabelText("Condition type"),
      "lifecycle_stage",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Add step to If it matches" }),
    );
    await user.type(
      within(dialog).getByLabelText("Task title, step 1 of If it matches"),
      "Call them",
    );
    await user.selectOptions(
      within(dialog).getByLabelText("Step to add to Otherwise"),
      "add_tag",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Add step to Otherwise" }),
    );
    // Only the actions the engine runs are offered.
    const kinds = within(
      within(dialog).getByLabelText("Step to add to If it matches"),
    )
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(kinds).toEqual(["Create task", "Add tag", "Assign owner", "Wait"]);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(
      within(dialog).getByRole("button", { name: "Create draft" }),
    );
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        name: "Welcome form leads",
        definition: {
          trigger: { type: "contact_created", sources: ["form"] },
          condition: { field: "lifecycle_stage", op: "in", values: ["lead"] },
          yes: [
            {
              type: "create_task",
              title: "Call them",
              priority: "medium",
              due_minutes: 60,
              assignee: "contact_owner",
            },
          ],
          no: [{ type: "add_tag", tag_id: TAG }],
        },
      });
    });
  });

  it("activates with the version and says why a refusal happened", async () => {
    const user = userEvent.setup();
    const { headersSent } = renderApp(
      `/w/${WS}/automations`,
      workspace(true, {
        onWrite: () => ({
          status: 422,
          body: {
            detail: {
              code: "invalid_automation",
              rule: "yes: at least one action",
            },
          },
        }),
      }),
    );
    const card = await screen.findByRole("listitem", {
      name: "Welcome form leads",
    });
    await user.click(within(card).getByRole("button", { name: "Activate" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent(
      "Some steps are incomplete",
    );
    const call = headersSent.find(
      (r) => r.method === "POST" && r.path.endsWith("/activate"),
    );
    expect(call?.headers["if-match"]).toBe('"2"');
  });

  it("shows a run's steps and opens its contact", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(`/w/${WS}/automations`, workspace(true));
    const card = await screen.findByRole("listitem", {
      name: "Welcome form leads",
    });
    await user.click(within(card).getByRole("button", { name: "Show runs" }));
    const table = await within(card).findByRole("table", {
      name: "Latest runs",
    });
    expect(table).toHaveTextContent("Completed");
    expect(table).toHaveTextContent("1 done, 0 skipped · yes branch");
    await user.click(
      within(table).getByRole("button", { name: "Open contact" }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/contacts`);
    });
    expect(router.state.location.search).toEqual({ record: CONTACT });
  });
});
