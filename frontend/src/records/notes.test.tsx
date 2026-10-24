import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/* Notes and history in the drawers (slice 3B.4, decision P3-B). */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const SAM = "d0000000-0000-4000-8000-000000000001";
const ACME = "c0000000-0000-4000-8000-000000000001";
const MINE = "e0000000-0000-4000-8000-000000000001";
const THEIRS = "e0000000-0000-4000-8000-000000000002";
const OTHER_USER = "bbbbbbbb-0000-4000-8000-000000000002";

const stamp = "2026-10-23T09:30:00+00:00";
const OWNER_ACTIONS = {
  read_members: true,
  create_contact: true,
  update_contact: true,
  delete_contact: true,
  create_note: true,
  edit_any_note: false,
  delete_any_note: false,
};
const READ_ONLY = { read_members: true };

const sam = {
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
  version: 1,
  archived_at: null as string | null,
};

function note(id: string, body: string, author: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    contact_id: SAM,
    company_id: null,
    body,
    author_user_id: author,
    created_at: stamp,
    updated_at: stamp,
    updated_by_user_id: author,
    edited: false,
    version: 1,
    can_edit: author === "u-me",
    can_delete: author === "u-me",
    ...extra,
  };
}

const HOSTILE = '<img src=x onerror="alert(1)"> & line one\nline two';
const mine = note(MINE, "Called about the renewal.", "u-me");
const theirs = note(THEIRS, HOSTILE, OTHER_USER, { edited: true });

function entry(id: string, kind: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    kind,
    occurred_at: stamp,
    actor_user_id: "u-me",
    fields: null,
    stage_from: null,
    stage_to: null,
    owner_from: null,
    owner_to: null,
    company_id: null,
    company_name: null,
    note_id: null,
    note_excerpt: null,
    note_truncated: false,
    ...extra,
  };
}

const history = [
  entry("f1", "note_added", { note_id: MINE, note_excerpt: "Called about the renewal." }),
  entry("f2", "stage_changed", { stage_from: "lead", stage_to: "customer" }),
  entry("f3", "updated", { fields: ["email", "city"] }),
  entry("f4", "company_unlinked", { company_id: ACME }),
  entry("f5", "created", { actor_user_id: null }),
];

interface Options {
  actions?: Record<string, boolean>;
  archived?: boolean;
  overrides?: Handler;
}

function crm({ actions = OWNER_ACTIONS, archived = false, overrides = () => undefined }: Options = {}): Handler {
  const record = { ...sam, archived_at: archived ? stamp : null };
  return (method, path, body) => {
    const custom = overrides(method, path, body);
    if (custom) return custom;
    if (method !== "GET") return undefined;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: ME, roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
      return { status: 200, body: { items: [record], next_cursor: null, total: 1, total_capped: false } };
    }
    if (path === `/v1/workspaces/${WS}/contacts/${SAM}`) return { status: 200, body: record };
    if (path.startsWith(`/v1/workspaces/${WS}/contacts/${SAM}/notes?`)) {
      const rights = actions.create_note ? {} : { can_edit: false, can_delete: false };
      const items = [mine, theirs].map((n) => ({
        ...n,
        ...rights,
        ...(archived ? { can_edit: false } : {}),
      }));
      return { status: 200, body: { items, next_cursor: null, record_archived: archived } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/contacts/${SAM}/activity?`)) {
      return { status: 200, body: { items: history, next_cursor: null } };
    }
    return undefined;
  };
}

const openSam = (options?: Options) => renderApp(`/w/${WS}/contacts?record=${SAM}`, crm(options));

async function notesSection() {
  const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
  return within(drawer).findByRole("region", { name: "Notes" });
}

describe("notes and activity in the drawer", () => {
  it("shows notes as plain text and the history in words, and passes an accessibility scan", async () => {
    openSam();
    const notes = await notesSection();
    expect(await within(notes).findByText("Called about the renewal.")).toBeInTheDocument();
    // Markup in a note is shown as text, never rendered.
    const hostile = within(notes).getByText((_, element) => element?.textContent === HOSTILE);
    expect(hostile.tagName).toBe("P");
    expect(document.querySelector('img[src="x"]')).toBeNull();
    expect(within(notes).getByText(/Edited/)).toBeInTheDocument();

    const activity = await screen.findByRole("region", { name: "Activity" });
    expect(await within(activity).findByText("Stage changed from Lead to Customer")).toBeInTheDocument();
    expect(within(activity).getByText("Updated email and city")).toBeInTheDocument();
    expect(within(activity).getByText("Unlinked from a deleted company")).toBeInTheDocument();
    expect(within(activity).getByText("Note added")).toBeInTheDocument();
    expect(within(activity).getByText(/System/)).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("adds a note with an idempotency key and clears the composer", async () => {
    const user = userEvent.setup();
    const added = note("e0000000-0000-4000-8000-000000000009", "Sent the quote.", "u-me");
    const { sent, headersSent } = openSam({
      overrides: (method, path) =>
        method === "POST" && path === `/v1/workspaces/${WS}/contacts/${SAM}/notes`
          ? { status: 201, body: added }
          : undefined,
    });
    const notes = await notesSection();
    const box = await within(notes).findByRole("textbox", { name: "New note" });
    expect(within(notes).getByRole("button", { name: /Add note/ })).toBeDisabled();
    await user.type(box, "  Sent the quote.  ");
    await user.click(within(notes).getByRole("button", { name: /Add note/ }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toEqual([
        {
          method: "POST",
          path: `/v1/workspaces/${WS}/contacts/${SAM}/notes`,
          body: { body: "  Sent the quote.  " },
        },
      ]);
    });
    const posted = headersSent.find((r) => r.method === "POST");
    expect(posted?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    await waitFor(() => {
      expect(box).toHaveValue("");
    });
  });

  it("lets the author edit their own note with its version, and not other people's", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = openSam({
      overrides: (method, path) =>
        method === "PATCH" && path === `/v1/workspaces/${WS}/notes/${MINE}`
          ? { status: 200, body: { ...mine, body: "Called twice.", version: 2, edited: true } }
          : undefined,
    });
    const notes = await notesSection();
    await within(notes).findByText("Called about the renewal.");
    const cards = within(notes).getAllByRole("listitem");
    expect(within(cards[1] as HTMLElement).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(within(cards[1] as HTMLElement).queryByRole("button", { name: /Delete/ })).toBeNull();

    await user.click(within(cards[0] as HTMLElement).getByRole("button", { name: /Edit/ }));
    const field = within(notes).getByRole("textbox", { name: "Note text" });
    await user.clear(field);
    await user.type(field, "Called twice.");
    await user.click(within(notes).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toEqual([
        { method: "PATCH", path: `/v1/workspaces/${WS}/notes/${MINE}`, body: { body: "Called twice." } },
      ]);
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"1"');
  });

  it("explains an edit refused because someone changed the note meanwhile", async () => {
    const user = userEvent.setup();
    openSam({
      overrides: (method, path) =>
        method === "PATCH" && path === `/v1/workspaces/${WS}/notes/${MINE}`
          ? { status: 409, body: { detail: { code: "stale_version", current_version: 3 } } }
          : undefined,
    });
    const notes = await notesSection();
    await within(notes).findByText("Called about the renewal.");
    await user.click(within(notes).getAllByRole("button", { name: /Edit/ })[0] as HTMLElement);
    await user.type(within(notes).getByRole("textbox", { name: "Note text" }), " Again.");
    await user.click(within(notes).getByRole("button", { name: "Save" }));
    expect(await within(notes).findByRole("alert")).toHaveTextContent(/Someone changed this note/);
  });

  it("deletes a note only after confirmation", async () => {
    const user = userEvent.setup();
    const { sent } = openSam({
      overrides: (method, path) =>
        method === "DELETE" && path === `/v1/workspaces/${WS}/notes/${MINE}` ? { status: 204 } : undefined,
    });
    const notes = await notesSection();
    await within(notes).findByText("Called about the renewal.");
    await user.click(within(notes).getByRole("button", { name: /Delete/ }));
    const confirm = await screen.findByRole("alertdialog", { name: "Delete note?" });
    expect(sent.filter((r) => r.method === "DELETE")).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "DELETE")).toEqual([
        { method: "DELETE", path: `/v1/workspaces/${WS}/notes/${MINE}`, body: undefined },
      ]);
    });
  });

  it("gives a read-only member the notes without a composer or note controls", async () => {
    openSam({ actions: READ_ONLY });
    const notes = await notesSection();
    expect(await within(notes).findByText("Called about the renewal.")).toBeInTheDocument();
    expect(within(notes).queryByRole("textbox")).toBeNull();
    expect(within(notes).queryByRole("button", { name: /Edit|Delete|Add note/ })).toBeNull();
  });

  it("asks to restore an archived record before adding or editing notes", async () => {
    openSam({ archived: true });
    const notes = await notesSection();
    expect(await within(notes).findByText("Restore this contact to add or edit notes.")).toBeInTheDocument();
    expect(within(notes).queryByRole("textbox")).toBeNull();
    expect(within(notes).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(within(notes).getByRole("button", { name: /Delete/ })).toBeInTheDocument();
  });

  it("asks before closing the drawer with an unsaved note", async () => {
    const user = userEvent.setup();
    openSam();
    const notes = await notesSection();
    await user.type(await within(notes).findByRole("textbox", { name: "New note" }), "Half a thought");
    await user.click(screen.getByRole("button", { name: "Close" }));
    const ask = await screen.findByRole("alertdialog", { name: "Discard note?" });
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Contact preview" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Contact preview" })).toBeNull();
    });
  });
});
