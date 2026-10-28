import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Settings › Business profile: locale, time zone, currency (decision P2-F 1)
 * and business hours (decision P5-B).
 */

const WS = "11111111-2222-4333-8444-555555555555";
const defaults = {
  locale: "en",
  time_zone: "Europe/Amsterdam",
  currency: "EUR",
  business_hours: null,
  version: 0,
  updated_at: null,
  updated_by_user_id: null,
};

function app(canEdit: boolean, overrides: Handler = () => undefined, stored: object = defaults): Handler {
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
    if (method === "GET" && path === `/v1/workspaces/${WS}/settings`) return { status: 200, body: stored };
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
    expect(within(form).getByText(/address are not available yet/)).toBeInTheDocument();
    expect(within(form).getByText(/No business hours are set/)).toBeInTheDocument();
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

  it("sets business hours from the suggested week and saves them with the version", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = open(
      app(true, (method) => (method === "PATCH" ? { status: 200, body: { ...defaults, version: 1 } } : undefined)),
    );
    const form = await screen.findByRole("form", { name: "Business profile" });
    await user.click(await within(form).findByRole("button", { name: "Set business hours" }));
    expect(within(form).getByRole("switch", { name: "Monday" })).toBeChecked();
    expect(within(form).getByRole("switch", { name: "Sunday" })).not.toBeChecked();
    // Saturday opens 10:00-14:00.
    await user.click(within(form).getByRole("switch", { name: "Saturday" }));
    // A time input takes its value whole, as a browser's time picker sets it.
    fireEvent.change(within(form).getByLabelText("Saturday opens at"), { target: { value: "10:00" } });
    fireEvent.change(within(form).getByLabelText("Saturday closes at"), { target: { value: "14:00" } });
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    });
    const day = { opens: "09:00", closes: "17:00" };
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({
      business_hours: [day, day, day, day, day, { opens: "10:00", closes: "14:00" }, null],
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"0"');
  });

  it("refuses a day that closes before it opens and clears the hours on request", async () => {
    const user = userEvent.setup();
    const day = { opens: "09:00", closes: "17:00" };
    const stored = { ...defaults, business_hours: [day, day, day, day, day, null, null], version: 4 };
    const { sent } = open(
      app(true, (method) => (method === "PATCH" ? { status: 200, body: { ...defaults, version: 5 } } : undefined), stored),
    );
    const form = await screen.findByRole("form", { name: "Business profile" });
    fireEvent.change(await within(form).findByLabelText("Monday closes at"), { target: { value: "08:00" } });
    expect(within(form).getByRole("alert")).toHaveTextContent(/closing time after its opening time/);
    expect(within(form).getByRole("button", { name: "Save changes" })).toBeDisabled();
    await user.click(within(form).getByRole("button", { name: "Clear business hours" }));
    expect(within(form).getByText(/No business hours are set/)).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ business_hours: null });
  });

  it("shows the hours read-only to members who may not change them", async () => {
    const day = { opens: "09:00", closes: "17:00" };
    open(app(false, undefined, { ...defaults, business_hours: [day, day, day, day, day, null, null], version: 2 }));
    const form = await screen.findByRole("form", { name: "Business profile" });
    expect(await within(form).findByRole("switch", { name: "Monday" })).toBeDisabled();
    expect(within(form).getByLabelText("Monday opens at")).toBeDisabled();
    expect(within(form).queryByRole("button", { name: "Clear business hours" })).toBeNull();
    expect(within(form).getAllByText("Closed")).toHaveLength(2);
  });
});
