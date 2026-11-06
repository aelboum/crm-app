import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Email templates (decision P7-T): Campaigns lists them; members who may
 * manage campaigns add one (the server checks the placeholders); a
 * template fills in a new campaign's subject and text; Read-only members
 * only read.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const stamp = "2026-11-02T09:30:00+00:00";
const TEMPLATE = {
  id: "e1000000-0000-4000-8000-000000000001",
  name: "Follow up",
  subject: "Hello {{first_name}}",
  body: "Dear {{first_name}},\nthank you.",
  created_at: stamp,
  updated_at: stamp,
  version: 1,
};

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  manage: boolean,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [manage ? "Member" : "Read-only"],
          actions: { read_campaigns: true, manage_campaigns: manage },
        },
      };
    }
    if (path === `${base}/campaigns`)
      return { status: 200, body: { items: [], sending_available: false } };
    if (path === `${base}/email-templates`)
      return { status: 200, body: { items: [TEMPLATE] } };
    return undefined;
  };
}

describe("email templates", () => {
  it("lists templates and adds one", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/campaigns`,
      workspace(true, (method) =>
        method === "POST" ? { status: 201, body: TEMPLATE } : undefined,
      ),
    );
    const panel = await screen.findByRole("region", {
      name: "Email templates",
    });
    expect(await within(panel).findByText("Follow up")).toBeInTheDocument();
    await user.click(
      within(panel).getByRole("button", { name: "New template" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "New template" });
    await user.type(within(dialog).getByLabelText("Template name"), "Welcome");
    await user.type(within(dialog).getByLabelText("Subject"), "Welcome");
    await user.type(within(dialog).getByLabelText("Text"), "Hi there");
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(
      within(dialog).getByRole("button", { name: "Save template" }),
    );
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        name: "Welcome",
        subject: "Welcome",
        body: "Hi there",
      });
    });
  });

  it("previews the text as a contact would get it", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace(true));
    const panel = await screen.findByRole("region", { name: "Email templates" });
    await user.click(await within(panel).findByRole("button", { name: "New template" }));
    const dialog = await screen.findByRole("dialog", { name: "New template" });
    // `{` starts a keyboard descriptor in user-event, so `{{` types one brace.
    await user.type(within(dialog).getByLabelText("Subject"), "Hello {{{{first_name}}");
    await user.type(
      within(dialog).getByLabelText("Text"),
      "Dear {{{{ first_name }} {{{{last_name}},{{{{unknown}}!",
    );
    const preview = within(dialog).getByRole("region", {
      name: "Preview, as sent to Ada Lovelace",
    });
    expect(preview).toHaveTextContent("Hello Ada");
    expect(preview).toHaveTextContent("Dear Ada Lovelace,!");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("fills a new campaign from a template", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/campaigns`, workspace(true));
    await user.click(
      await screen.findByRole("button", { name: "New campaign" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(
      await within(dialog).findByLabelText("Use a template"),
      TEMPLATE.id,
    );
    expect(within(dialog).getByLabelText("Subject")).toHaveValue(
      "Hello {{first_name}}",
    );
    expect(within(dialog).getByLabelText("Message")).toHaveValue(
      "Dear {{first_name}},\nthank you.",
    );
  });

  it("lets Read-only members only read", async () => {
    renderApp(`/w/${WS}/campaigns`, workspace(false));
    const panel = await screen.findByRole("region", {
      name: "Email templates",
    });
    await within(panel).findByText("Follow up");
    expect(within(panel).queryByRole("button")).toBeNull();
  });
});
