import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi } from "vitest";

import { fileDownload, fileNameFrom } from "../api/exportContacts";
import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Contacts CSV export (slice 3E): the Export button follows `/access`, sends
 * the list's current filters and order without paging, saves the file under
 * the server's name, and explains every refusal without retrying.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const EXPORT_PATH = `/v1/workspaces/${WS}/contacts/export.csv`;
const CAN_EXPORT = { read_members: true, create_contact: true, export_records: true };
const CANNOT_EXPORT = { read_members: true, create_contact: true, export_records: false };

const sam = {
  id: "d0000000-0000-4000-8000-000000000001",
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
  owner_user_id: "u-me",
  created_at: "2026-10-23T09:30:00+00:00",
  updated_at: "2026-10-23T09:30:00+00:00",
  created_by_user_id: "u-me",
  updated_by_user_id: "u-me",
  version: 1,
  archived_at: null,
};

interface Reply {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
}

function workspace(actions: Record<string, boolean>, exportReply?: () => Reply): Handler {
  return (method, path) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) {
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    }
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return {
        status: 200,
        body: {
          items: [{ membership_id: "m1", user_id: "u-me", status: "active", roles: ["Owner"] }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
      return { status: 200, body: { items: [sam], next_cursor: null, total: 1, total_capped: false } };
    }
    if (method === "GET" && path.startsWith(EXPORT_PATH) && exportReply) return exportReply();
    return undefined;
  };
}

const csvReply = (): Reply => ({
  status: 200,
  body: "id,first_name\r\n",
  headers: {
    "Content-Type": "text/csv; charset=utf-8",
    "Content-Disposition": 'attachment; filename="contacts-2026-10-26.csv"',
  },
});

let save: MockInstance<(blob: Blob, fileName: string) => void>;
beforeEach(() => {
  save = vi.spyOn(fileDownload, "save").mockImplementation(() => undefined);
});
afterEach(() => {
  save.mockRestore();
});

describe("contacts export", () => {
  it("is offered to people who may export, and refused with a reason to others", async () => {
    const { unmount } = renderApp(`/w/${WS}/contacts`, workspace(CAN_EXPORT));
    expect(await screen.findByRole("button", { name: "Export" })).toBeEnabled();
    unmount();
    renderApp(`/w/${WS}/contacts`, workspace(CANNOT_EXPORT));
    const refused = await screen.findByRole("button", {
      name: "Export (Only Owners and Admins can export contacts)",
    });
    expect(refused).toBeDisabled();
  });

  it("exports the current search, filters, view and order, and saves the file under the server's name", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/contacts`, workspace(CAN_EXPORT, csvReply));
    await screen.findByRole("table", { name: "Contacts" });
    await user.type(screen.getByRole("searchbox", { name: "Search name or email" }), "Sam");
    await user.click(screen.getByRole("button", { name: "Stage" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "Customer" }));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Archived" }));
    await waitFor(() => {
      expect(sent.some((r) => r.path.includes("q=Sam") && r.path.includes("archived=true"))).toBe(true);
    });
    await user.click(await screen.findByRole("button", { name: /Updated/ }));
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
    const request = sent.find((r) => r.path.startsWith(EXPORT_PATH));
    const query = new URLSearchParams(request?.path.split("?")[1]);
    expect(query.get("q")).toBe("Sam");
    expect(query.getAll("lifecycle_stage")).toEqual(["customer"]);
    expect(query.get("archived")).toBe("true");
    expect(query.get("sort")).toBe("updated_at");
    expect(query.get("direction")).toBe("desc");
    expect(query.has("limit")).toBe(false);
    expect(query.has("cursor")).toBe(false);
    const [blob, fileName] = save.mock.calls[0] ?? [];
    expect(blob).toBeInstanceOf(Blob);
    expect(fileName).toBe("contacts-2026-10-26.csv");
    expect(document.querySelector(".toast-region")).toHaveTextContent("Contacts exported");
  });

  it("shows progress while the export runs, sends it once, and announces it", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/contacts`, workspace(CAN_EXPORT, csvReply));
    await screen.findByRole("table", { name: "Contacts" });
    const answer = globalThis.fetch;
    let release: () => void = () => undefined;
    vi.stubGlobal("fetch", async (request: Request) => {
      if (request.url.includes("export.csv")) {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      return answer(request);
    });
    await user.click(screen.getByRole("button", { name: "Export" }));
    const busy = await screen.findByRole("button", { name: "Exporting…" });
    expect(busy).toBeDisabled();
    expect(screen.getAllByRole("status").some((s) => s.textContent === "Exporting…")).toBe(true);
    expect(await accessibilityViolations()).toEqual([]);
    release();
    expect(await screen.findByRole("button", { name: "Export" })).toBeEnabled();
    expect(sent.filter((r) => r.path.startsWith(EXPORT_PATH))).toHaveLength(1);
  });

  it.each([
    [413, {}, "More than 50,000 contacts match. Narrow the search or filters, then export again."],
    [
      429,
      { "Retry-After": "1800" },
      "You have reached the limit of 10 exports per hour. Try again in 30 minutes.",
    ],
    [403, {}, "You do not have permission to export contacts."],
    [503, { "Retry-After": "5" }, "Export is temporarily unavailable. Try again in a few minutes."],
    [500, {}, "The export failed. Try again."],
  ])("explains a %i without retrying", async (status, headers, message) => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts`,
      workspace(CAN_EXPORT, () => ({ status, body: { detail: { code: "x" } }, headers })),
    );
    await user.click(await screen.findByRole("button", { name: "Export" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(save).not.toHaveBeenCalled();
    expect(sent.filter((r) => r.path.startsWith(EXPORT_PATH))).toHaveLength(1);
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("explains a network failure", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts`,
      workspace(CAN_EXPORT, () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Export" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We could not reach LeadStack. Check your connection and try again.",
    );
  });

  it("uses the server's file name only when it is a plain, safe name", () => {
    expect(fileNameFrom('attachment; filename="contacts-2026-10-26.csv"')).toBe(
      "contacts-2026-10-26.csv",
    );
    expect(fileNameFrom('attachment; filename="../../evil.csv"')).toBe("contacts.csv");
    expect(fileNameFrom('attachment; filename="report.exe"')).toBe("contacts.csv");
    expect(fileNameFrom('attachment; filename=".csv"')).toBe("contacts.csv");
    expect(fileNameFrom(null)).toBe("contacts.csv");
  });
});
