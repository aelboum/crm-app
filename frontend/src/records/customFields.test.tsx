import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Custom fields (decision P3-D): the drawer's "Custom fields" card, typed
 * inputs in the contact dialog that send only changed keys, the server's
 * refusal of one value, and Settings › Custom fields. The server enforces
 * every permission; these tests check what the screens offer and send.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const SAM = "d0000000-0000-4000-8000-000000000001";
const stamp = "2026-10-23T09:30:00+00:00";

function definition(key: string, label: string, field_type: string, extra: Record<string, unknown> = {}) {
  return {
    id: `f0000000-0000-4000-8000-${key.padStart(12, "0").slice(-12).replace(/[^0-9a-f]/g, "0")}`,
    entity: "contact",
    key,
    label,
    field_type,
    options: null,
    position: 0,
    version: 1,
    archived: false,
    created_at: stamp,
    updated_at: stamp,
    ...extra,
  };
}

const FIELDS = [
  definition("carrier", "Carrier", "text", { id: "f0000000-0000-4000-8000-000000000001" }),
  definition("seats", "Seats", "number", { id: "f0000000-0000-4000-8000-000000000002" }),
  definition("renewal", "Renewal", "date", { id: "f0000000-0000-4000-8000-000000000003" }),
  definition("vip", "VIP", "boolean", { id: "f0000000-0000-4000-8000-000000000004" }),
  definition("tier", "Tier", "select", { id: "f0000000-0000-4000-8000-000000000005", options: ["Gold", "Silver"] }),
  definition("old", "Old field", "text", { id: "f0000000-0000-4000-8000-000000000006", archived: true }),
  definition("plan", "Plan", "text", { id: "f0000000-0000-4000-8000-000000000007", entity: "company" }),
];

function sam(custom: Record<string, unknown>, version = 1) {
  return {
    id: SAM,
    first_name: "Sam",
    last_name: "Jansen",
    email: "sam@example.test",
    phone: null,
    job_title: null,
    city: null,
    lifecycle_stage: "customer",
    source: "manual",
    company_id: null,
    company: null,
    owner_user_id: null,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: "u-me",
    updated_by_user_id: "u-me",
    version,
    archived_at: null,
    tags: [],
    custom_fields: custom,
  };
}

const STORED = { carrier: "Delta", seats: 1234.5, renewal: "2027-01-31", vip: true, tier: "Gold" };
const OWNER = { read_members: true, create_contact: true, update_contact: true, update_workspace: true };
const MEMBER = { read_members: true, create_contact: true, update_contact: true, update_workspace: false };

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: { onPatch?: (body: unknown) => Reply; onPost?: (path: string, body: unknown) => Reply } = {},
): Handler {
  return (method, path, body) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/custom-fields`) {
      return { status: 200, body: { items: FIELDS, max_active: 50 } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/tags`) return { status: 200, body: { items: [], max_tags: 500 } };
    if (method === "GET" && path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
      return { status: 200, body: { items: [sam(STORED)], next_cursor: null, total: 1, total_capped: false } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/contacts/${SAM}`) return { status: 200, body: sam(STORED) };
    if (method === "PATCH" && path === `/v1/workspaces/${WS}/contacts/${SAM}`) return options.onPatch?.(body);
    if (method === "POST") return options.onPost?.(path, body);
    if (path.includes("/notes") || path.includes("/activity")) {
      return { status: 200, body: { items: [], next_cursor: null, record_archived: false } };
    }
    return undefined;
  };
}

describe("custom fields on records", () => {
  it("shows the active fields' values in the drawer, with Manage for Owners and Admins", async () => {
    const { unmount } = renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace(OWNER));
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    const card = await within(drawer).findByRole("region", { name: "Custom fields" });
    const rows = within(card)
      .getAllByRole("term")
      .map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(rows).toEqual([
      ["Carrier", "Delta"],
      ["Seats", "1,234.5"],
      ["Renewal", "Jan 31, 2027"],
      ["VIP", "Yes"],
      ["Tier", "Gold"],
    ]);
    expect(within(card).getByRole("link", { name: "Manage" })).toHaveAttribute(
      "href",
      `/app/w/${WS}/settings?section=fields`,
    );
    expect(await accessibilityViolations()).toEqual([]);
    unmount();
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace(MEMBER));
    const memberCard = await screen.findByRole("region", { name: "Custom fields" });
    expect(within(memberCard).queryByRole("link", { name: "Manage" })).toBeNull();
  });

  it("edits values with typed inputs and sends only the changed keys", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(MEMBER, { onPatch: () => ({ status: 200, body: sam({ seats: 12, renewal: "2027-01-31", vip: true, tier: "Silver" }, 2) }) }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit contact" });
    expect(within(dialog).queryByLabelText("Old field")).toBeNull(); // archived
    expect(within(dialog).getByLabelText("Seats")).toHaveAttribute("type", "number");
    expect(within(dialog).getByLabelText("Renewal")).toHaveAttribute("type", "date");
    await user.clear(within(dialog).getByLabelText("Carrier"));
    await user.clear(within(dialog).getByLabelText("Seats"));
    await user.type(within(dialog).getByLabelText("Seats"), "12");
    await user.selectOptions(within(dialog).getByLabelText("Tier"), "Silver");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({
        custom_fields: { carrier: null, seats: 12, tier: "Silver" },
      });
    });
  });

  it("marks the field whose value the server refused", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(MEMBER, {
        onPatch: () => ({ status: 422, body: { detail: { code: "invalid_custom_field", key: "carrier" } } }),
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit contact" });
    await user.type(within(dialog).getByLabelText("Carrier"), "!");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(within(dialog).getByLabelText("Carrier")).toHaveAttribute("aria-invalid", "true");
    });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This value is not valid for this field.");
  });
});

describe("settings › custom fields", () => {
  it("is read-only for Members and lists each entity's fields", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/settings?section=fields`, workspace(MEMBER));
    const list = await screen.findByRole("list", { name: "Contacts" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(6);
    expect(within(list).getByText(/old · Text · archived/)).toBeInTheDocument();
    expect(screen.getByText("Only Owners and Admins can add, change or archive fields.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "New field" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Companies" }));
    const companies = await screen.findByRole("list", { name: "Companies" });
    expect(within(companies).getAllByRole("listitem")).toHaveLength(1);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("adds a choice field with a key suggested from its label, and archives a field", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/settings?section=fields`,
      workspace(OWNER, {
        onPost: (path) =>
          path.endsWith("/archive")
            ? { status: 200, body: { ...FIELDS[0], archived: true, version: 2 } }
            : { status: 201, body: definition("insurance_carrier", "Insurance carrier", "select", { options: ["A", "B"] }) },
      }),
    );
    const form = await screen.findByRole("form", { name: "New field" });
    await user.type(within(form).getByLabelText("Label"), "Insurance carrier");
    expect(within(form).getByLabelText("Key")).toHaveValue("insurance_carrier");
    await user.selectOptions(within(form).getByLabelText("Type"), "select");
    await user.type(within(form).getByLabelText("Options"), "A{Enter}B");
    await user.click(within(form).getByRole("button", { name: "Add field" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({
        entity: "contact",
        key: "insurance_carrier",
        label: "Insurance carrier",
        field_type: "select",
        position: 6,
        options: ["A", "B"],
      });
    });
    await user.click(screen.getByRole("button", { name: "Archive Carrier" }));
    await waitFor(() => {
      expect(sent.some((r) => r.method === "POST" && r.path.endsWith(`${FIELDS[0]?.id ?? ""}/archive`))).toBe(true);
    });
  });
});
