import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/* Settings › Business profile: locale, time zone, currency (decision P2-F 1). */

const WS = "11111111-2222-4333-8444-555555555555";
const defaults = {
  locale: "en",
  time_zone: "Europe/Amsterdam",
  currency: "EUR",
  version: 0,
  updated_at: null,
  updated_by_user_id: null,
};

function app(canEdit: boolean, overrides: Handler = () => undefined): Handler {
  return (method, path, body) => {
    const custom = overrides(method, path, body);
    if (custom) return custom;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) {
      return { status: 200, body: { id: WS, name: "Acme Studio", status: "active" } };
    }
    if (path === `/v1/workspaces/${WS}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [canEdit ? "Owner" : "Read-only"],
          actions: { read_members: true, update_workspace: canEdit },
        },
      };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/settings`) return { status: 200, body: defaults };
    return undefined;
  };
}

const open = (handler: Handler) => renderApp(`/w/${WS}/settings?section=business`, handler);

describe("business profile settings", () => {
  it("shows the stored settings, an example and what is not available, and passes an accessibility scan", async () => {
    open(app(true));
    const form = await screen.findByRole("form", { name: "Business profile" });
    expect(await within(form).findByLabelText("Time zone")).toHaveValue("Europe/Amsterdam");
    expect(within(form).getByLabelText("Default currency")).toHaveValue("EUR");
    expect(within(form).getByLabelText("Workspace name")).toBeDisabled();
    expect(within(form).getByText(/Example:/)).toBeInTheDocument();
    expect(within(form).getByText(/business hours are not available yet/)).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("saves only the changed field with the version it was read at", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = open(
      app(true, (method, path) =>
        method === "PATCH" && path === `/v1/workspaces/${WS}/settings`
          ? { status: 200, body: { ...defaults, currency: "USD", version: 1 } }
          : undefined,
      ),
    );
    const form = await screen.findByRole("form", { name: "Business profile" });
    await user.selectOptions(await within(form).findByLabelText("Default currency"), "USD");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toEqual([
        { method: "PATCH", path: `/v1/workspaces/${WS}/settings`, body: { currency: "USD" } },
      ]);
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"0"');
  });

  it("explains a save refused because someone else changed the settings", async () => {
    const user = userEvent.setup();
    open(
      app(true, (method) =>
        method === "PATCH" ? { status: 409, body: { detail: { code: "stale_version", current_version: 3 } } } : undefined,
      ),
    );
    const form = await screen.findByRole("form", { name: "Business profile" });
    await user.selectOptions(await within(form).findByLabelText("Default currency"), "GBP");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/Someone else changed these settings/);
    expect(within(form).getByRole("button", { name: "Load the latest" })).toBeInTheDocument();
  });

  it("shows members who may not change them the values without controls", async () => {
    open(app(false));
    const form = await screen.findByRole("form", { name: "Business profile" });
    expect(await within(form).findByLabelText("Default currency")).toBeDisabled();
    expect(within(form).getByLabelText("Time zone")).toBeDisabled();
    expect(within(form).queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(within(form).getByText(/Only Owners and Admins can change these settings/)).toBeInTheDocument();
  });
});
