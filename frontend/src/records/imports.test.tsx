import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * CSV import (decision P3-F): the Import button follows `/access`; choosing
 * a file sends it and shows the counts and refused rows; a changed mapping
 * is checked again; importing follows the job's progress; refusals are
 * explained. The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const IMPORT = "e0000000-0000-4000-8000-000000000001";
const stamp = "2026-10-27T09:30:00+00:00";

function summary(extra: Record<string, unknown> = {}) {
  return {
    id: IMPORT,
    entity: "contact",
    status: "previewed",
    mapping: { first_name: 0, email: 1 },
    total_rows: 4,
    valid_rows: 2,
    invalid_rows: 1,
    duplicate_rows: 1,
    created_rows: 0,
    skipped_rows: 0,
    failed_rows: 0,
    cancel_requested: false,
    created_by_user_id: "u-me",
    created_at: stamp,
    updated_at: stamp,
    finished_at: null,
    errors: [
      { row: 2, field: "email", code: "invalid" },
      { row: 3, field: null, code: "duplicate" },
    ],
    ...extra,
  };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: { onPreview?: () => Reply; onGet?: () => Reply } = {},
): Handler {
  return (method, path) => {
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/contacts?`)) {
      return { status: 200, body: { items: [], next_cursor: null, total: 0, total_capped: false } };
    }
    if (method === "POST" && path.startsWith(`/v1/workspaces/${WS}/imports?`)) return options.onPreview?.();
    if (method === "POST" && path === `/v1/workspaces/${WS}/imports/${IMPORT}/commit`) {
      return { status: 200, body: summary({ status: "queued" }) };
    }
    if (method === "GET" && path === `/v1/workspaces/${WS}/imports/${IMPORT}`) return options.onGet?.();
    return undefined;
  };
}

const OWNER = { read_members: true, create_contact: true, import_records: true };
const MEMBER = { read_members: true, create_contact: true, import_records: false };
const csv = () => new File(["first_name,email\nSam,sam@example.test\n"], "people.csv", { type: "text/csv" });
const checked = (): Reply => ({ status: 201, body: { summary: summary(), header: ["First", "Mail"], sample: [] } });

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Import" }));
  const dialog = await screen.findByRole("dialog", { name: "Import contacts" });
  await user.upload(within(dialog).getByLabelText("CSV file"), csv());
  return dialog;
}

describe("CSV import", () => {
  it("is offered to Owners and Admins only", async () => {
    const { unmount } = renderApp(`/w/${WS}/contacts`, workspace(OWNER));
    expect(await screen.findByRole("button", { name: "Import" })).toBeEnabled();
    unmount();
    renderApp(`/w/${WS}/contacts`, workspace(MEMBER));
    expect(
      await screen.findByRole("button", { name: "Import (Only Owners and Admins can import)" }),
    ).toBeDisabled();
  });

  it("checks the chosen file, shows what will not be imported, and checks a new mapping", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/contacts`, workspace(OWNER, { onPreview: checked }));
    const dialog = await chooseFile(user);
    expect(await within(dialog).findByText("Ready to import")).toBeInTheDocument();
    const first = sent.find((r) => r.method === "POST");
    expect(new URLSearchParams(first?.path.split("?")[1]).get("entity")).toBe("contact");
    expect(within(dialog).getByRole("table", { name: "Rows that will not be imported" })).toHaveTextContent(
      "Duplicate of an existing record or an earlier row",
    );
    expect(within(dialog).getByLabelText("First name")).toHaveValue("0");
    expect(within(dialog).getByRole("link", { name: "Download the error report" })).toHaveAttribute(
      "href",
      `/v1/workspaces/${WS}/imports/${IMPORT}/errors.csv`,
    );
    expect(await accessibilityViolations()).toEqual([]);

    await user.selectOptions(within(dialog).getByLabelText("Email"), "1");
    await user.selectOptions(within(dialog).getByLabelText("First name"), "");
    await user.selectOptions(within(dialog).getByLabelText("Last name"), "0");
    await user.click(within(dialog).getByRole("button", { name: "Check again with these columns" }));
    await waitFor(() => {
      const previews = sent.filter((r) => r.method === "POST");
      expect(previews).toHaveLength(2);
      const query = new URLSearchParams(previews[1]?.path.split("?")[1]);
      expect(query.getAll("column").sort()).toEqual(["email:1", "last_name:0"]);
    });
  });

  it("imports and follows the progress until it finishes", async () => {
    const user = userEvent.setup();
    let polls = 0;
    renderApp(
      `/w/${WS}/contacts`,
      workspace(OWNER, {
        onPreview: checked,
        onGet: () => {
          polls += 1;
          return {
            status: 200,
            body:
              polls < 2
                ? summary({ status: "running", created_rows: 1 })
                : summary({ status: "completed_with_errors", created_rows: 2, finished_at: stamp }),
          };
        },
      }),
    );
    const dialog = await chooseFile(user);
    await user.click(await within(dialog).findByRole("button", { name: "Import 2 rows" }));
    expect(
      await within(dialog).findByText("Import finished; some rows were not imported.", {}, { timeout: 6000 }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("status")).toHaveTextContent("2 created, 0 skipped, 0 failed.");
  }, 10_000);

  it.each([
    [413, { code: "file_too_large", max_bytes: 5242880 }, "The file is larger than 5 MB."],
    [422, { code: "too_many_rows" }, "more than 10,000 rows"],
    [422, { code: "required_field_unmapped" }, "Choose the column that holds the required name."],
    [429, { code: "x" }, "You have checked 10 files in the last hour."],
  ])("explains a %i refusal of the file", async (status, detail, message) => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/contacts`, workspace(OWNER, { onPreview: () => ({ status, body: { detail } }) }));
    const dialog = await chooseFile(user);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    expect(within(dialog).queryByRole("button", { name: /^Import \d/ })).toBeNull();
  });
});
