import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const ACME = "c0000000-0000-4000-8000-000000000001";
const SAM = "d0000000-0000-4000-8000-000000000001";
const RIA = "d0000000-0000-4000-8000-000000000002";
const NEW = "d0000000-0000-4000-8000-000000000003";

const OWNER_ACTIONS = {
  read_members: true,
  create_contact: true,
  update_contact: true,
  delete_contact: true,
  create_company: true,
  update_company: true,
  delete_company: true,
};
const READ_ONLY = { read_members: true };

const stamp = "2026-10-23T09:30:00+00:00";
const base = {
  owner_user_id: null,
  created_at: stamp,
  updated_at: stamp,
  created_by_user_id: "u-me",
  updated_by_user_id: "u-me",
  version: 1,
  archived_at: null,
};

const acme = {
  ...base,
  id: ACME,
  name: "Acme BV",
  domain: "acme.example",
  website: "https://acme.example",
  phone: null,
  industry: "Logistics",
  city: "Utrecht",
  country_code: "NL",
};

function contact(id: string, first: string, extra: Record<string, unknown> = {}) {
  return {
    ...base,
    id,
    first_name: first,
    last_name: "Jansen",
    email: `${first.toLowerCase()}@example.test`,
    phone: null,
    job_title: null,
    city: null,
    lifecycle_stage: "lead",
    source: "manual",
    company_id: null,
    company: null,
    ...extra,
  };
}

const sam = contact(SAM, "Sam", {
  lifecycle_stage: "customer",
  owner_user_id: "u-me",
  company_id: ACME,
  company: { id: ACME, name: "Acme BV", archived: false },
  job_title: "Buyer",
});
const ria = contact(RIA, "Ria");

const page = (items: unknown[], next: string | null = null) => ({
  status: 200,
  body: { items, next_cursor: next, total: items.length, total_capped: false },
});

function crm(actions: Record<string, boolean>, overrides: Handler = () => undefined): Handler {
  return (method, path, body) => {
    const custom = overrides(method, path, body);
    if (custom) return custom;
    if (method !== "GET") return undefined;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === `/v1/workspaces/${WS}`) {
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    }
    if (path === `/v1/workspaces/${WS}/access`) {
      return { status: 200, body: { membership_id: ME, roles: ["Owner"], actions } };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/members?`)) {
      return {
        status: 200,
        body: {
          items: [
            { membership_id: ME, user_id: "u-me", status: "active", roles: ["Owner"] },
            { membership_id: "m2", user_id: "u-2", status: "active", roles: ["Member"] },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        },
      };
    }
    if (path.startsWith(`/v1/workspaces/${WS}/contacts?`)) return page([sam, ria]);
    if (path === `/v1/workspaces/${WS}/contacts/${SAM}`) return { status: 200, body: sam };
    if (path === `/v1/workspaces/${WS}/contacts/${RIA}`) return { status: 200, body: ria };
    if (path.startsWith(`/v1/workspaces/${WS}/companies?`)) return page([acme]);
    if (path === `/v1/workspaces/${WS}/companies/${ACME}`) return { status: 200, body: acme };
    return undefined;
  };
}

const listRequests = (sent: { method: string; path: string }[], kind: string) =>
  sent.filter((r) => r.method === "GET" && r.path.startsWith(`/v1/workspaces/${WS}/${kind}?`));

describe("contacts", () => {
  it("lists contacts with stage, owner and company, and passes an accessibility scan", async () => {
    renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS));
    expect(await screen.findByRole("heading", { level: 1, name: /Contacts/ })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Contacts" });
    const samRow = within(table).getByRole("button", { name: "Sam Jansen" }).closest("tr");
    if (!samRow) throw new Error("row not found");
    expect(within(samRow).getByText("Customer")).toBeInTheDocument();
    expect(within(samRow).getByText("You")).toBeInTheDocument();
    expect(within(samRow).getByText("Acme BV")).toBeInTheDocument();
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Import/ })).toBeDisabled();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("offers a read-only member no way to change records", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/contacts`, crm(READ_ONLY));
    await user.click(await screen.findByRole("button", { name: "Sam Jansen" }));
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    expect(await within(drawer).findByText("sam@example.test")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New contact" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Archive" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: "Delete permanently" })).toBeNull();
  });

  it("sends search, stage and view filters to the API", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS));
    await screen.findByRole("table", { name: "Contacts" });
    await user.type(screen.getByRole("searchbox", { name: "Search name or email" }), "sa");
    await waitFor(() => {
      expect(listRequests(sent, "contacts").some((r) => r.path.includes("q=sa"))).toBe(true);
    });
    await user.click(screen.getByRole("button", { name: "Stage" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "Customer" }));
    await waitFor(() => {
      expect(
        listRequests(sent, "contacts").some((r) => r.path.includes("lifecycle_stage=customer")),
      ).toBe(true);
    });
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Archived" }));
    await waitFor(() => {
      expect(listRequests(sent, "contacts").some((r) => r.path.includes("archived=true"))).toBe(
        true,
      );
    });
  });

  it("checks the form before sending, then creates with an idempotency key and opens the contact", async () => {
    const user = userEvent.setup();
    const created = contact(NEW, "Noor", { last_name: null });
    const { sent, headersSent } = renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path) => {
        if (method === "POST" && path === `/v1/workspaces/${WS}/contacts`) {
          return { status: 201, body: created };
        }
        if (method === "GET" && path === `/v1/workspaces/${WS}/contacts/${NEW}`) {
          return { status: 200, body: created };
        }
        return undefined;
      }),
    );
    await user.click(await screen.findByRole("button", { name: "New contact" }));
    const dialog = await screen.findByRole("dialog", { name: "New contact" });
    await user.click(within(dialog).getByRole("button", { name: "Create contact" }));
    expect(within(dialog).getByText("First name is required")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Add an email or phone number")).toHaveLength(2);
    expect(sent.filter((r) => r.method === "POST")).toEqual([]);

    await user.type(within(dialog).getByLabelText(/First name/), "Noor");
    await user.type(within(dialog).getByLabelText("Email"), "noor@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Create contact" }));

    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({
      first_name: "Noor",
      last_name: null,
      email: "noor@example.test",
      phone: null,
      job_title: null,
      city: null,
      company_id: null,
      lifecycle_stage: "lead",
      source: "manual",
      owner_user_id: null,
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(
      /^[0-9a-f]{32}$/,
    );
    expect(await screen.findByText("Contact created · Noor")).toBeInTheDocument();
    expect(await screen.findByRole("dialog", { name: "Contact preview" })).toBeInTheDocument();
  });

  it("points to the existing contact when the email is taken", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path) =>
        method === "POST" && path === `/v1/workspaces/${WS}/contacts`
          ? { status: 409, body: { detail: { code: "duplicate_email", existing_id: SAM } } }
          : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "New contact" }));
    const dialog = await screen.findByRole("dialog", { name: "New contact" });
    await user.type(within(dialog).getByLabelText(/First name/), "Sam");
    await user.type(within(dialog).getByLabelText("Email"), "sam@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Create contact" }));
    expect(
      await within(dialog).findByText("A contact with this email already exists."),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Open existing" }));
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    expect(await within(drawer).findByText("sam@example.test")).toBeInTheDocument();
  });

  it("edits only the changed fields, with the version it read", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      crm(OWNER_ACTIONS, (method) =>
        method === "PATCH"
          ? { status: 200, body: { ...sam, city: "Delft", version: 2 } }
          : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: /Edit/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit contact" });
    await user.type(within(dialog).getByLabelText("City"), "Delft");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toEqual([
        { method: "PATCH", path: `/v1/workspaces/${WS}/contacts/${SAM}`, body: { city: "Delft" } },
      ]);
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"1"');
  });

  it("explains a change made by someone else in the meantime", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      crm(OWNER_ACTIONS, (method) =>
        method === "PATCH"
          ? { status: 409, body: { detail: { code: "stale_version", current_version: 2 } } }
          : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: /Edit/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit contact" });
    await user.type(within(dialog).getByLabelText("City"), "Delft");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await within(dialog).findByText(/Someone changed this record/)).toBeInTheDocument();
  });

  it("deletes permanently only after confirmation", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      crm(OWNER_ACTIONS, (method) => (method === "DELETE" ? { status: 204 } : undefined)),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: "Delete permanently" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Delete contact?" });
    expect(sent.filter((r) => r.method === "DELETE")).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "DELETE")).toEqual([
        { method: "DELETE", path: `/v1/workspaces/${WS}/contacts/${SAM}`, body: undefined },
      ]);
    });
    expect(await screen.findByText("Deleted permanently")).toBeInTheDocument();
  });

  it("says a deleted contact is gone, not that the workspace is missing", async () => {
    const gone = "d0000000-0000-4000-8000-0000000000ff";
    renderApp(
      `/w/${WS}/contacts?record=${gone}`,
      crm(OWNER_ACTIONS, (method, path) =>
        method === "GET" && path === `/v1/workspaces/${WS}/contacts/${gone}`
          ? { status: 404, body: { detail: "Not Found" } }
          : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    expect(await within(drawer).findByText(/This contact no longer exists/)).toBeInTheDocument();
    expect(within(drawer).queryByText(/workspace does not exist/)).toBeNull();
  });

  it("loads the next page by cursor", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path) => {
        if (method !== "GET" || !path.startsWith(`/v1/workspaces/${WS}/contacts?`)) return undefined;
        return path.includes("cursor=next1") ? page([ria]) : page([sam], "next1");
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("button", { name: "Ria Jansen" })).toBeInTheDocument();
    expect(listRequests(sent, "contacts").some((r) => r.path.includes("cursor=next1"))).toBe(true);
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});

describe("companies", () => {
  it("lists companies and passes an accessibility scan", async () => {
    renderApp(`/w/${WS}/companies`, crm(OWNER_ACTIONS));
    const table = await screen.findByRole("table", { name: "Companies" });
    expect(within(table).getByRole("button", { name: "Acme BV" })).toBeInTheDocument();
    expect(within(table).getByText("acme.example")).toBeInTheDocument();
    expect(within(table).getByText("Logistics")).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("shows a company's people and opens one in Contacts", async () => {
    const user = userEvent.setup();
    const { sent, router } = renderApp(`/w/${WS}/companies?record=${ACME}`, crm(OWNER_ACTIONS));
    const drawer = await screen.findByRole("dialog", { name: "Company" });
    await user.click(await within(drawer).findByRole("button", { name: /Sam Jansen/ }));
    expect(
      listRequests(sent, "contacts").some((r) => r.path.includes(`company_id=${ACME}`)),
    ).toBe(true);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/contacts`);
    });
    expect(await screen.findByRole("dialog", { name: "Contact preview" })).toBeInTheDocument();
  });

  it("requires a name and reports a taken domain", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/companies`,
      crm(OWNER_ACTIONS, (method) =>
        method === "POST"
          ? { status: 409, body: { detail: { code: "duplicate_domain", existing_id: ACME } } }
          : undefined,
      ),
    );
    await user.click(await screen.findByRole("button", { name: "New company" }));
    const dialog = await screen.findByRole("dialog", { name: "New company" });
    await user.click(within(dialog).getByRole("button", { name: "Create company" }));
    expect(within(dialog).getByText("Company name is required")).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "POST")).toEqual([]);
    await user.type(within(dialog).getByLabelText(/Company name/), "Acme 2");
    await user.type(within(dialog).getByLabelText("Website"), "https://www.acme.example");
    await user.click(within(dialog).getByRole("button", { name: "Create company" }));
    expect(
      await within(dialog).findByText("A company with this domain already exists."),
    ).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
      name: "Acme 2",
      website: "https://www.acme.example",
      domain: null,
    });
  });
});

// --- Slice 3A hardening -----------------------------------------------------

const BETA = "c0000000-0000-4000-8000-000000000002";
const ZETA = "c0000000-0000-4000-8000-000000000003";
const ZERO = "c0000000-0000-4000-8000-000000000004";
const company = (id: string, name: string) => ({ ...acme, id, name, domain: null, website: null, city: null });
const beta = company(BETA, "Beta Freight");
const zeta = company(ZETA, "Zeta Ltd");
const zero = company(ZERO, "Zero Co");

/** Companies by search text and cursor, as the API pages them. */
const companyPages: Handler = (method, path) => {
  if (method !== "GET" || !path.startsWith(`/v1/workspaces/${WS}/companies?`)) return undefined;
  const query = new URLSearchParams(path.split("?")[1]);
  const q = query.get("q");
  if (q === "Zet") return page([zeta]);
  if (q === "Ze") return page([zero]);
  if (q) return page([]);
  return query.get("cursor") === "co2" ? page([beta]) : page([acme], "co2");
};

const delay = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

async function openNewContact(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "New contact" }));
  return screen.findByRole("dialog", { name: "New contact" });
}

describe("company picker", () => {
  it("finds companies beyond the first page and by search, and links the chosen one", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path, body) =>
        method === "POST"
          ? { status: 201, body: { ...ria, ...(body as object), id: NEW } }
          : companyPages(method, path, body),
      ),
    );
    const dialog = await openNewContact(user);
    await user.type(within(dialog).getByLabelText(/First name/), "Noor");
    await user.type(within(dialog).getByLabelText("Email"), "noor@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Choose company" }));
    const results = await within(dialog).findByRole("listbox", { name: "Companies" });
    expect(within(results).getByRole("option", { name: /Acme BV/ })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);

    // The second page, by cursor.
    await user.click(within(dialog).getByRole("button", { name: "Load more companies" }));
    expect(await within(dialog).findByRole("option", { name: /Beta Freight/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Load more companies" })).toBeNull();

    // A search, sent to the workspace's own list of active companies.
    await user.type(within(dialog).getByRole("searchbox", { name: "Search companies" }), "Zet");
    await user.click(await within(dialog).findByRole("option", { name: /Zeta Ltd/ }));
    expect(within(dialog).getByText("Zeta Ltd")).toBeInTheDocument();
    // Focus returns to the company control, not to the top of the form.
    expect(within(dialog).getByRole("button", { name: "Change company" })).toHaveFocus();
    expect(
      listRequests(sent, "companies").some((r) => r.path.includes("q=Zet") && r.path.includes("archived=false")),
    ).toBe(true);

    await user.click(within(dialog).getByRole("button", { name: "Create contact" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({ company_id: ZETA });
    });
  });

  it("never lets an older, slower search replace a newer one", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS, companyPages));
    const answer = globalThis.fetch;
    vi.stubGlobal("fetch", async (request: Request) => {
      if (new URL(request.url).searchParams.get("q") === "Ze") await delay(700);
      return answer(request);
    });
    const dialog = await openNewContact(user);
    await user.click(within(dialog).getByRole("button", { name: "Choose company" }));
    const box = within(dialog).getByRole("searchbox", { name: "Search companies" });
    await user.type(box, "Ze");
    await delay(350); // past the debounce: the slow "Ze" request is out
    await user.type(box, "t");
    expect(await within(dialog).findByRole("option", { name: /Zeta Ltd/ })).toBeInTheDocument();
    await delay(800); // the slow answer has now arrived
    expect(within(dialog).queryByRole("option", { name: /Zero Co/ })).toBeNull();
    expect(within(dialog).getByRole("option", { name: /Zeta Ltd/ })).toBeInTheDocument();
  });

  it("says when nothing matches, and offers a retry when the list fails", async () => {
    const user = userEvent.setup();
    let failing = false;
    renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path, body) =>
        failing && path.startsWith(`/v1/workspaces/${WS}/companies?`)
          ? { status: 500, body: { detail: "Internal Server Error" } }
          : companyPages(method, path, body),
      ),
    );
    const dialog = await openNewContact(user);
    await user.click(within(dialog).getByRole("button", { name: "Choose company" }));
    const box = within(dialog).getByRole("searchbox", { name: "Search companies" });
    await user.type(box, "Nope");
    expect(await within(dialog).findByText("No active company starts with that text.")).toBeInTheDocument();
    failing = true;
    await user.type(box, "s");
    expect(
      await within(dialog).findByText("Something went wrong. Try again.", {}, { timeout: 8000 }),
    ).toBeInTheDocument();
    failing = false;
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByText("No active company starts with that text.")).toBeInTheDocument();
  }, 15000);

  it("moves into the results with the down arrow, and Escape closes only the search", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS, companyPages));
    const dialog = await openNewContact(user);
    await user.type(within(dialog).getByLabelText(/First name/), "Noor");
    await user.click(within(dialog).getByRole("button", { name: "Choose company" }));
    await within(dialog).findByRole("option", { name: /Acme BV/ });
    await user.keyboard("{ArrowDown}");
    expect(within(dialog).getByRole("option", { name: /Acme BV/ })).toHaveFocus();
    await user.keyboard("{Escape}");
    // The contact dialog and what was typed stay; focus is back on the control.
    expect(screen.getByRole("dialog", { name: "New contact" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/First name/)).toHaveValue("Noor");
    expect(within(dialog).queryByRole("searchbox", { name: "Search companies" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Choose company" })).toHaveFocus();
    // Opening again starts from an empty search.
    await user.click(within(dialog).getByRole("button", { name: "Choose company" }));
    expect(within(dialog).getByRole("searchbox", { name: "Search companies" })).toHaveValue("");
  });

  it("shows a contact's current company and can remove it", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      crm(OWNER_ACTIONS, (method) =>
        method === "PATCH"
          ? { status: 200, body: { ...sam, company_id: null, company: null, version: 2 } }
          : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: /Edit/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit contact" });
    expect(within(dialog).getByText("Acme BV")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Remove company" }));
    expect(within(dialog).getByText("No company")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Choose company" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({ company_id: null });
    });
  });
});

describe("form accessibility", () => {
  it("ties the server's field errors to the select and the company controls", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method) =>
        method === "POST"
          ? {
              status: 422,
              body: {
                detail: [
                  { loc: ["body", "lifecycle_stage"], msg: "x", type: "x" },
                  { loc: ["body", "company_id"], msg: "x", type: "x" },
                ],
              },
            }
          : undefined,
      ),
    );
    const dialog = await openNewContact(user);
    await user.type(within(dialog).getByLabelText(/First name/), "Noor");
    await user.type(within(dialog).getByLabelText("Email"), "noor@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Create contact" }));
    const stage = within(dialog).getByRole("combobox", { name: "Stage" });
    await waitFor(() => {
      expect(stage).toHaveAttribute("aria-invalid", "true");
    });
    expect(stage).toHaveAccessibleDescription("Check this value.");
    expect(within(dialog).getByRole("button", { name: "Choose company" })).toHaveAccessibleDescription(
      "Check this value.",
    );
    expect(await accessibilityViolations()).toEqual([]);
  });
});

describe("company drawer people", () => {
  const people =
    (fail: boolean): Handler =>
    (method, path) => {
      if (method !== "GET" || !path.startsWith(`/v1/workspaces/${WS}/contacts?`)) return undefined;
      if (!path.includes("cursor=p2")) return page([sam], "p2");
      return fail ? { status: 500, body: { detail: "Internal Server Error" } } : page([ria]);
    };

  it("loads more people by cursor until the end", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/companies?record=${ACME}`, crm(OWNER_ACTIONS, people(false)));
    const drawer = await screen.findByRole("dialog", { name: "Company" });
    expect(await within(drawer).findByRole("button", { name: /Sam Jansen/ })).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Load more people" }));
    expect(await within(drawer).findByRole("button", { name: /Ria Jansen/ })).toBeInTheDocument();
    expect(within(drawer).getByText("All 2 people shown.")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Load more people" })).toBeNull();
    const next = listRequests(sent, "contacts").find((r) => r.path.includes("cursor=p2"));
    expect(next?.path).toContain(`company_id=${ACME}`);
  });

  it("keeps the people shown when the next page fails", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/companies?record=${ACME}`, crm(OWNER_ACTIONS, people(true)));
    const drawer = await screen.findByRole("dialog", { name: "Company" });
    await user.click(await within(drawer).findByRole("button", { name: "Load more people" }));
    expect(await within(drawer).findByText("More people could not be loaded.", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: /Sam Jansen/ })).toBeInTheDocument();
  }, 15000);
});

describe("records regressions", () => {
  it("archives a contact from the drawer and confirms it", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      crm(OWNER_ACTIONS, (method, path) =>
        method === "POST" && path.endsWith("/archive")
          ? { status: 200, body: { ...sam, archived_at: stamp } }
          : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    await user.click(await within(drawer).findByRole("button", { name: "Archive" }));
    await waitFor(() => {
      expect(
        sent.some((r) => r.method === "POST" && r.path === `/v1/workspaces/${WS}/contacts/${SAM}/archive`),
      ).toBe(true);
    });
    const toasts = document.querySelector(".toast-region");
    expect(toasts).not.toBeNull();
    await waitFor(() => {
      expect(toasts).toHaveTextContent("Archived");
    });
  });

  it("restores an archived contact, and explains when another active one holds its email", async () => {
    const user = userEvent.setup();
    const archived = { ...ria, archived_at: stamp };
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${RIA}`,
      crm(OWNER_ACTIONS, (method, path) => {
        if (method === "POST" && path.endsWith("/restore")) {
          return { status: 409, body: { detail: { code: "duplicate_email", existing_id: SAM } } };
        }
        if (method === "GET" && path === `/v1/workspaces/${WS}/contacts/${RIA}`) {
          return { status: 200, body: archived };
        }
        return undefined;
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "Contact preview" });
    expect(await within(drawer).findByText(/Archived: hidden from the default list/)).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Restore" }));
    expect(
      await within(drawer).findByText(
        "Another active contact already has this email, so this one cannot be restored.",
      ),
    ).toBeInTheDocument();
    expect(sent.some((r) => r.method === "POST" && r.path.endsWith(`/contacts/${RIA}/restore`))).toBe(true);
  });

  it("filters by owner and sorts by name and by last update", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS));
    await screen.findByRole("table", { name: "Contacts" });
    await user.click(screen.getByRole("button", { name: "Owner" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "You" }));
    await waitFor(() => {
      expect(listRequests(sent, "contacts").some((r) => r.path.includes("owner=u-me"))).toBe(true);
    });
    await user.keyboard("{Escape}");

    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending");
    await user.click(within(screen.getByRole("columnheader", { name: /Name/ })).getByRole("button"));
    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "descending");
    });
    expect(listRequests(sent, "contacts").some((r) => r.path.includes("direction=desc") && r.path.includes("sort=name"))).toBe(true);
    await user.click(within(screen.getByRole("columnheader", { name: /Updated/ })).getByRole("button"));
    await waitFor(() => {
      expect(
        listRequests(sent, "contacts").some((r) => r.path.includes("sort=updated_at") && r.path.includes("direction=desc")),
      ).toBe(true);
    });
  });

  it("says a list is forbidden, without a retry", async () => {
    renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path) =>
        method === "GET" && path.startsWith(`/v1/workspaces/${WS}/contacts?`)
          ? { status: 403, body: { detail: "Not authorized." } }
          : undefined,
      ),
    );
    expect(await screen.findByText("You do not have permission to see this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("offers a retry after a server error, and recovers", async () => {
    const user = userEvent.setup();
    let failing = true;
    renderApp(
      `/w/${WS}/companies`,
      crm(OWNER_ACTIONS, (method, path) =>
        failing && method === "GET" && path.startsWith(`/v1/workspaces/${WS}/companies?`)
          ? { status: 500, body: { detail: "Internal Server Error" } }
          : undefined,
      ),
    );
    const retry = await screen.findByRole("button", { name: "Try again" }, { timeout: 8000 });
    failing = false;
    await user.click(retry);
    expect(await screen.findByRole("table", { name: "Companies" })).toBeInTheDocument();
  }, 15000);

  it("opens the new-contact dialog from the header's link", async () => {
    renderApp(`/w/${WS}/contacts?create=contact`, crm(OWNER_ACTIONS));
    expect(await screen.findByRole("dialog", { name: "New contact" })).toBeInTheDocument();
  });

  it("ignores the new-contact link for a read-only member", async () => {
    renderApp(`/w/${WS}/contacts?create=contact`, crm(READ_ONLY));
    await screen.findByRole("table", { name: "Contacts" });
    expect(screen.queryByRole("dialog", { name: "New contact" })).toBeNull();
  });

  it("edits a company's changed fields with the version it read", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/companies?record=${ACME}`,
      crm(OWNER_ACTIONS, (method) =>
        method === "PATCH" ? { status: 200, body: { ...acme, city: "Delft", version: 2 } } : undefined,
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: "Company" });
    await user.click(await within(drawer).findByRole("button", { name: /Edit/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit company" });
    const city = within(dialog).getByLabelText("City");
    await user.clear(city);
    await user.type(city, "Delft");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toEqual([
        { method: "PATCH", path: `/v1/workspaces/${WS}/companies/${ACME}`, body: { city: "Delft" } },
      ]);
    });
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"1"');
  });
});

describe("narrow screens", () => {
  /** Answers the width media queries as a 390 px phone would. */
  function narrowScreen() {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
  }

  it("keeps the contacts page usable and the switcher named, with navigation behind a button", async () => {
    narrowScreen();
    renderApp(`/w/${WS}/contacts`, crm(OWNER_ACTIONS));
    expect(await screen.findByRole("button", { name: "Open navigation" })).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Contacts" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Acme Client workspace" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Company" })).toHaveClass("hide-narrow");
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("names the workspace switcher while the workspace name is unavailable", async () => {
    narrowScreen();
    renderApp(
      `/w/${WS}/contacts`,
      crm(OWNER_ACTIONS, (method, path) =>
        method === "GET" && path === `/v1/workspaces/${WS}` ? { status: 503, body: { detail: "x" } } : undefined,
      ),
    );
    expect(await screen.findByRole("button", { name: "Client workspace" })).toBeInTheDocument();
  });
});
