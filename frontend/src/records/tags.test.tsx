import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Tags (decision P3-C): pills in lists and drawers, the Tag filter, the
 * drawer's tag dialog (one versioned save; Owners and Admins can create a
 * tag there) and Settings › Tags. The server enforces every permission;
 * these tests check what the screens offer and what they send.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const SAM = "d0000000-0000-4000-8000-000000000001";
const VIP = { id: "a0000000-0000-4000-8000-000000000001", name: "VIP" };
const HOT = { id: "a0000000-0000-4000-8000-000000000002", name: "Hot lead" };
const COLD = { id: "a0000000-0000-4000-8000-000000000003", name: "Cold" };
const WARM = { id: "a0000000-0000-4000-8000-000000000004", name: "Warm" };
const stamp = "2026-10-23T09:30:00+00:00";
const tagOut = (tag: { id: string; name: string }) => ({ ...tag, version: 1, created_at: stamp, updated_at: stamp });

const OWNER = {
  read_members: true,
  create_contact: true,
  update_contact: true,
  update_workspace: true,
};
const MEMBER = { read_members: true, create_contact: true, update_contact: true, update_workspace: false };
const READER = { read_members: true, create_contact: false, update_contact: false, update_workspace: false };

function sam(tags: { id: string; name: string }[], version = 1) {
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
    tags,
  };
}

type Reply = { status: number; body?: unknown } | undefined;

interface Options {
  actions: Record<string, boolean>;
  tags?: { id: string; name: string }[];
  record?: ReturnType<typeof sam>;
  onPut?: (body: unknown) => Reply;
  onTag?: (method: string, path: string, body: unknown) => Reply;
}

function workspace({ actions, tags = [VIP, HOT, COLD], record = sam([VIP, HOT]), onPut, onTag }: Options): Handler {
  return (method, path, body) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/tags`) {
      return { status: 200, body: { items: tags.map(tagOut), max_tags: 500 } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/tags`)) return onTag?.(method, path, body);
    if (method === "GET" && path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
      return { status: 200, body: { items: [record], next_cursor: null, total: 1, total_capped: false } };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/contacts/${SAM}`) return { status: 200, body: record };
    if (method === "PUT" && path === `/v1/workspaces/${WS}/contacts/${SAM}/tags`) return onPut?.(body);
    if (path.includes("/notes") || path.includes("/activity")) {
      return { status: 200, body: { items: [], next_cursor: null, record_archived: false } };
    }
    return undefined;
  };
}

async function openTagDialog(user: ReturnType<typeof userEvent.setup>) {
  const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
  await user.click(await within(drawer).findByRole("button", { name: "Edit tags" }));
  return screen.findByRole("dialog", { name: "Edit tags" });
}

describe("tags on records", () => {
  it("shows a record's first tags in the list and filters by any chosen tag", async () => {
    const user = userEvent.setup();
    const many = sam([VIP, HOT, COLD, WARM]);
    const { sent } = renderApp(`/w/${WS}/contacts`, workspace({ actions: READER, record: many }));
    const table = await screen.findByRole("table", { name: "Contacts" });
    const pills = await within(table).findByRole("list", { name: "Tags" });
    expect(within(pills).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "VIP",
      "Hot lead",
      "Cold",
      "+1",
    ]);
    await user.click(screen.getByRole("button", { name: "Tags" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "VIP" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Cold" }));
    await user.keyboard("{Escape}");
    await waitFor(() => {
      const listed = sent.filter((r) => r.path.startsWith(`/v1/workspaces/${WS}/contacts?`));
      const query = new URLSearchParams(listed.at(-1)?.path.split("?")[1]);
      expect(query.getAll("tag_id")).toEqual([VIP.id, COLD.id]);
    });
  });

  it("offers no tag editing to people who may not change the record", async () => {
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace({ actions: READER }));
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    expect(await within(drawer).findByText("VIP")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Edit tags" })).toBeNull();
  });

  it("saves the chosen set once, with the version it read", async () => {
    const user = userEvent.setup();
    const { headersSent, sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace({ actions: MEMBER, onPut: () => ({ status: 200, body: sam([HOT, COLD], 2) }) }),
    );
    const dialog = await openTagDialog(user);
    expect(within(dialog).getByText("2 of 20 tags chosen")).toBeInTheDocument();
    // A Member chooses among existing tags only.
    expect(within(dialog).queryByRole("textbox", { name: "New tag" })).toBeNull();
    await user.click(within(dialog).getByRole("checkbox", { name: "VIP" }));
    await user.click(within(dialog).getByRole("checkbox", { name: "Cold" }));
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Save tags" }));
    await waitFor(() => {
      expect(document.querySelector(".toast-region")).toHaveTextContent("Tags saved");
    });
    const puts = sent.filter((r) => r.method === "PUT");
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ tag_ids: [HOT.id, COLD.id] });
    expect(headersSent.find((r) => r.method === "PUT")?.headers["if-match"]).toBe('"1"');
  });

  it("filters the dialog's tags and explains a change made meanwhile", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace({
        actions: MEMBER,
        onPut: () => ({ status: 409, body: { detail: { code: "stale_version", current_version: 3 } } }),
      }),
    );
    const dialog = await openTagDialog(user);
    await user.type(within(dialog).getByRole("searchbox", { name: "Find a tag" }), "co");
    expect(within(dialog).getAllByRole("checkbox").map((box) => box.closest("label")?.textContent)).toEqual([
      "Cold",
    ]);
    await user.click(within(dialog).getByRole("button", { name: "Save tags" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Someone changed this record meanwhile");
  });

  it("lets Owners and Admins create a tag in the dialog, which is then chosen", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace({
        actions: OWNER,
        onTag: (method) => (method === "POST" ? { status: 201, body: tagOut(WARM) } : undefined),
        onPut: () => ({ status: 200, body: sam([HOT, VIP, WARM], 2) }),
      }),
    );
    const dialog = await openTagDialog(user);
    await user.type(within(dialog).getByRole("textbox", { name: "New tag" }), "Warm");
    await user.click(within(dialog).getByRole("button", { name: "Add tag" }));
    await waitFor(() => {
      expect(within(dialog).getByText("3 of 20 tags chosen")).toBeInTheDocument();
    });
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({ name: "Warm" });
    await user.click(within(dialog).getByRole("button", { name: "Save tags" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PUT")?.body).toEqual({ tag_ids: [VIP.id, HOT.id, WARM.id] });
    });
  });

  it("allows at most 20 tags on a record", async () => {
    const user = userEvent.setup();
    const vocabulary = Array.from({ length: 22 }, (_, n) => ({
      id: `b0000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
      name: `Tag ${String(n).padStart(2, "0")}`,
    }));
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace({ actions: MEMBER, tags: vocabulary, record: sam(vocabulary.slice(0, 20)) }),
    );
    const dialog = await openTagDialog(user);
    expect(within(dialog).getByText("20 of 20 tags chosen")).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "Tag 21" })).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: "Tag 00" }));
    expect(within(dialog).getByRole("checkbox", { name: "Tag 21" })).toBeEnabled();
  });
});

describe("settings › tags", () => {
  it("is read-only for Members", async () => {
    renderApp(`/w/${WS}/settings?section=tags`, workspace({ actions: MEMBER }));
    const list = await screen.findByRole("list", { name: "Tags" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["VIP", "Hot lead", "Cold"]);
    expect(screen.getByText("Only Owners and Admins can add, rename or delete tags.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete VIP" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "New tag" })).toBeNull();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("adds, renames with the version it read, and deletes after confirming", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/settings?section=tags`,
      workspace({
        actions: OWNER,
        onTag: (method, path) => {
          if (method === "POST") return { status: 201, body: tagOut(WARM) };
          if (method === "PATCH") return { status: 200, body: { ...tagOut(VIP), name: "VIPs", version: 2 } };
          if (method === "DELETE" && path.endsWith(HOT.id)) return { status: 204 };
          return undefined;
        },
      }),
    );
    await screen.findByRole("list", { name: "Tags" });
    await user.type(screen.getByRole("textbox", { name: "New tag" }), "Warm");
    await user.click(screen.getByRole("button", { name: "Add tag" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toEqual({ name: "Warm" });
    });

    await user.click(screen.getByRole("button", { name: "Rename VIP" }));
    const field = screen.getByRole("textbox", { name: "New name for VIP" });
    expect(field).toHaveFocus();
    await user.clear(field);
    await user.type(field, "VIPs{Enter}");
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ name: "VIPs" });
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"1"');

    await user.click(screen.getByRole("button", { name: "Delete Hot lead" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Delete this tag?" });
    expect(confirm).toHaveTextContent("removed from every contact and company");
    await user.click(within(confirm).getByRole("button", { name: "Delete tag" }));
    await waitFor(() => {
      expect(sent.some((r) => r.method === "DELETE" && r.path.endsWith(HOT.id))).toBe(true);
    });
  });

  it("explains a duplicate name", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/settings?section=tags`,
      workspace({
        actions: OWNER,
        onTag: () => ({ status: 409, body: { detail: { code: "duplicate_tag", existing_id: VIP.id } } }),
      }),
    );
    await screen.findByRole("list", { name: "Tags" });
    await user.type(screen.getByRole("textbox", { name: "New tag" }), "vip");
    await user.click(screen.getByRole("button", { name: "Add tag" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A tag with this name already exists.");
  });
});
