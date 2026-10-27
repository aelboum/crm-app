import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Settings › Sales pipeline (decision P4, slice 4A): everyone sees the
 * stages; Owners and Admins (`manage_pipeline`) rename the pipeline and add,
 * edit, reorder and remove stages, each change sending the version it was
 * made from. The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const PIPE = "b0000000-0000-4000-8000-000000000001";
const stamp = "2026-10-27T09:30:00+00:00";
const STAGES = [
  { id: "c0000000-0000-4000-8000-000000000001", name: "Qualified", probability: 20, position: 0 },
  { id: "c0000000-0000-4000-8000-000000000002", name: "Meeting", probability: 40, position: 1 },
  { id: "c0000000-0000-4000-8000-000000000003", name: "Proposal", probability: 60, position: 2 },
];

function pipeline(version = 1, stages = STAGES, name = "Sales") {
  return { id: PIPE, name, version, created_at: stamp, updated_at: stamp, stages };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  onChange?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/pipelines`) {
      return { status: 200, body: { items: [pipeline()], max_stages: 15 } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/pipelines/${PIPE}`)) return onChange?.(method, path, body);
    return undefined;
  };
}

const OWNER = { read_members: true, manage_pipeline: true };
const MEMBER = { read_members: true, manage_pipeline: false };
const URL = `/w/${WS}/settings?section=pipeline`;

describe("settings › sales pipeline", () => {
  it("shows the stages in order, read-only for Members", async () => {
    renderApp(URL, workspace(MEMBER));
    const list = await screen.findByRole("list", { name: "Stages (3 of 15)" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "1Qualified20%",
      "2Meeting40%",
      "3Proposal60%",
    ]);
    expect(screen.getByText("Only Owners and Admins can change the pipeline.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Meeting" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "New stage" })).toBeNull();
    expect(screen.getByText("Sales")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("renames, adds, moves, edits and removes with the version it holds", async () => {
    const user = userEvent.setup();
    let version = 1;
    const { sent, headersSent } = renderApp(
      URL,
      workspace(OWNER, () => {
        version += 1;
        return { status: 200, body: pipeline(version) };
      }),
    );
    await screen.findByRole("list", { name: "Stages (3 of 15)" });
    expect(await accessibilityViolations()).toEqual([]);

    const name = screen.getByRole("textbox", { name: "Pipeline name" });
    await user.clear(name);
    await user.type(name, "New business");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ name: "New business" });
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"1"');

    await user.type(screen.getByRole("textbox", { name: "New stage" }), "Closing");
    const probability = screen.getByRole("spinbutton", { name: "Probability (%)" });
    await user.clear(probability);
    await user.type(probability, "90");
    await user.click(screen.getByRole("button", { name: "Add stage" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({ name: "Closing", probability: 90 });
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["if-match"]).toBe('"2"');

    expect(screen.getByRole("button", { name: "Move Qualified up" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move Qualified down" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PUT")?.body).toEqual({
        stage_ids: [STAGES[1]?.id, STAGES[0]?.id, STAGES[2]?.id],
      });
    });

    await user.click(screen.getByRole("button", { name: "Edit Meeting" }));
    const stageName = screen.getByRole("textbox", { name: "Name of Meeting" });
    expect(stageName).toHaveFocus();
    const editRow = stageName.closest("li");
    if (!editRow) throw new Error("no edit row");
    const stageProbability = within(editRow).getByRole("spinbutton", { name: "Probability (%)" });
    await user.clear(stageProbability);
    await user.type(stageProbability, "45{Enter}");
    await waitFor(() => {
      const patch = sent.filter((r) => r.method === "PATCH").at(-1);
      expect(patch?.path).toBe(`/v1/workspaces/${WS}/pipelines/${PIPE}/stages/${STAGES[1]?.id ?? ""}`);
      expect(patch?.body).toEqual({ probability: 45 });
    });

    await user.click(await screen.findByRole("button", { name: "Remove Proposal" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Remove stage?" });
    await user.click(within(confirm).getByRole("button", { name: "Remove stage" }));
    await waitFor(() => {
      expect(sent.some((r) => r.method === "DELETE" && r.path.endsWith(STAGES[2]?.id ?? "?"))).toBe(true);
    });
  });

  it("refuses a probability outside 0 to 100 before sending it", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace(OWNER));
    await screen.findByRole("list", { name: "Stages (3 of 15)" });
    await user.type(screen.getByRole("textbox", { name: "New stage" }), "Closing");
    const probability = screen.getByRole("spinbutton", { name: "Probability (%)" });
    await user.clear(probability);
    await user.type(probability, "150");
    await user.click(screen.getByRole("button", { name: "Add stage" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Probability must be a whole number from 0 to 100.");
    expect(sent.some((r) => r.method === "POST")).toBe(false);
  });

  it.each([
    [409, { code: "duplicate_stage" }, "Another stage already has this name."],
    [409, { code: "stale_version", current_version: 4 }, "Someone else changed the pipeline."],
    [409, { code: "stage_limit_reached" }, "at most 15 stages"],
    [403, { code: "forbidden" }, "You do not have permission to change the pipeline."],
  ])("explains a %i refusal (%j)", async (status, detail, message) => {
    const user = userEvent.setup();
    renderApp(URL, workspace(OWNER, () => ({ status, body: { detail } })));
    await screen.findByRole("list", { name: "Stages (3 of 15)" });
    await user.type(screen.getByRole("textbox", { name: "New stage" }), "Meeting2");
    await user.click(screen.getByRole("button", { name: "Add stage" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("keeps the last stage", async () => {
    const handler = workspace(OWNER);
    renderApp(URL, (method, path, body) => {
      if (method === "GET" && path === `/v1/workspaces/${WS}/pipelines`) {
        return { status: 200, body: { items: [pipeline(1, STAGES.slice(0, 1))], max_stages: 15 } };
      }
      return handler(method, path, body);
    });
    await screen.findByRole("list", { name: "Stages (1 of 15)" });
    expect(screen.getByRole("button", { name: "Remove Qualified" })).toBeDisabled();
  });
});
