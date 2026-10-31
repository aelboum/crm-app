import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * A contact's and a company's deals in their drawers (decision P4-E): the
 * list asks the server for that record's deals only, shows stage, outcome
 * and value, opens a deal on the Opportunities page, says when more exist
 * than it shows, and starts a new deal linked to the record. Who may create
 * follows `/access`; the server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const SAM = "d0000000-0000-4000-8000-000000000001";
const ACME = "e0000000-0000-4000-8000-000000000001";
const PIPE = "b0000000-0000-4000-8000-000000000001";
const S1 = "c0000000-0000-4000-8000-000000000001";
const S2 = "c0000000-0000-4000-8000-000000000002";
const D1 = "f0000000-0000-4000-8000-000000000001";
const D2 = "f0000000-0000-4000-8000-000000000002";
const stamp = "2026-10-31T09:30:00+00:00";
const STAGES = [
  { id: S1, name: "Qualified", probability: 20, position: 0 },
  { id: S2, name: "Proposal", probability: 60, position: 1 },
];
const acme = { id: ACME, name: "Acme", archived: false };

function deal(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    title: "Website redesign",
    amount: "12500.50",
    currency: "EUR",
    weighted_amount: "2500.10",
    pipeline_id: PIPE,
    stage_id: S1,
    stage: STAGES[0],
    stage_entered_at: stamp,
    owner_user_id: ME,
    expected_close_date: null,
    contact_id: SAM,
    contact: { id: SAM, name: "Sam Jansen", archived: false },
    company_id: ACME,
    company: acme,
    outcome: "open",
    lost_reason: null,
    closed_at: null,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: ME,
    updated_by_user_id: ME,
    version: 1,
    ...extra,
  };
}

const DEALS = [
  deal(D1),
  deal(D2, {
    title: "Support plan",
    amount: null,
    stage_id: S2,
    stage: STAGES[1],
    outcome: "won",
  }),
];

const sam = {
  id: SAM,
  first_name: "Sam",
  last_name: "Jansen",
  email: "sam@example.test",
  phone: null,
  job_title: null,
  city: null,
  lifecycle_stage: "lead",
  source: "manual",
  company_id: ACME,
  company: acme,
  owner_user_id: null,
  created_at: stamp,
  updated_at: stamp,
  created_by_user_id: ME,
  updated_by_user_id: ME,
  version: 1,
  archived_at: null,
  tags: [],
  custom_fields: {},
};

const company = {
  id: ACME,
  name: "Acme",
  domain: null,
  website: null,
  phone: null,
  industry: null,
  city: null,
  country_code: null,
  owner_user_id: null,
  created_at: stamp,
  updated_at: stamp,
  created_by_user_id: ME,
  updated_by_user_id: ME,
  version: 1,
  archived_at: null,
  tags: [],
  custom_fields: {},
};

const WRITER = {
  read_members: true,
  create_opportunity: true,
  update_contact: true,
  update_company: true,
};
const READER = { read_members: true, create_opportunity: false };

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  options: {
    deals?: unknown[];
    total?: number;
    onWrite?: (method: string, path: string, body: unknown) => Reply;
  } = {},
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (method !== "GET") return options.onWrite?.(method, path, body);
    if (path === "/auth/me") return { status: 200, body: { user_id: ME } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: { membership_id: "m1", roles: ["Owner"], actions },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: { items: [], total: 0, limit: 50, offset: 0 },
      };
    }
    if (path === `${base}/settings`) {
      return {
        status: 200,
        body: {
          locale: "en",
          time_zone: "Europe/Amsterdam",
          currency: "EUR",
          version: 1,
          updated_at: stamp,
          updated_by_user_id: null,
        },
      };
    }
    if (path === `${base}/pipelines`) {
      const pipeline = {
        id: PIPE,
        name: "Sales",
        version: 1,
        created_at: stamp,
        updated_at: stamp,
        stages: STAGES,
      };
      return { status: 200, body: { items: [pipeline], max_stages: 15 } };
    }
    if (path.startsWith(`${base}/opportunities?`)) {
      const items = options.deals ?? DEALS;
      return {
        status: 200,
        body: {
          items,
          next_cursor: null,
          total: options.total ?? items.length,
          total_capped: false,
        },
      };
    }
    if (path.startsWith(`${base}/contacts?`)) {
      return {
        status: 200,
        body: {
          items: [sam],
          next_cursor: null,
          total: 1,
          total_capped: false,
        },
      };
    }
    if (path === `${base}/contacts/${SAM}`) return { status: 200, body: sam };
    if (path.startsWith(`${base}/companies?`)) {
      return {
        status: 200,
        body: {
          items: [company],
          next_cursor: null,
          total: 1,
          total_capped: false,
        },
      };
    }
    if (path === `${base}/companies/${ACME}`)
      return { status: 200, body: company };
    return undefined;
  };
}

function dealCalls(sent: { method: string; path: string }[]) {
  return sent.filter(
    (r) =>
      r.method === "GET" &&
      r.path.startsWith(`/v1/workspaces/${WS}/opportunities?`),
  );
}

describe("a record's opportunities", () => {
  it("lists a contact's deals with stage, outcome and value, and opens one", async () => {
    const user = userEvent.setup();
    const { sent, router } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(WRITER),
    );
    const section = await screen.findByRole("region", {
      name: "Opportunities (2)",
    });
    const rows = within(section).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Website redesign");
    expect(rows[0]).toHaveTextContent("Qualified");
    expect(rows[0]).toHaveTextContent("12,500.50");
    expect(rows[1]).toHaveTextContent("Support plan");
    expect(rows[1]).toHaveTextContent("Won");
    const call = dealCalls(sent)[0];
    expect(call?.path).toContain(`contact_id=${SAM}`);
    expect(call?.path).not.toContain("outcome=");
    expect(await accessibilityViolations()).toEqual([]);

    await user.click(
      within(section).getByRole("button", { name: /Support plan/ }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WS}/opportunities`);
    });
    expect(router.state.location.search).toEqual({ record: D2 });
  });

  it("starts a new deal linked to the contact and its company", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(
      `/w/${WS}/contacts?record=${SAM}`,
      workspace(WRITER, {
        deals: [],
        onWrite: (method) =>
          method === "POST" ? { status: 201, body: deal(D1) } : undefined,
      }),
    );
    const section = await screen.findByRole("region", {
      name: "Opportunities",
    });
    expect(
      await within(section).findByText("No opportunities."),
    ).toBeInTheDocument();
    await user.click(
      await within(section).findByRole("button", { name: "New opportunity" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "New opportunity",
    });
    await user.type(
      within(dialog).getByLabelText("Opportunity name"),
      "Website redesign",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Create opportunity" }),
    );
    await waitFor(() => {
      expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
        title: "Website redesign",
        contact_id: SAM,
        company_id: ACME,
      });
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "New opportunity" }),
      ).toBeNull();
    });
  });

  it("lists a company's deals only, and says when there are more than it shows", async () => {
    const { sent } = renderApp(
      `/w/${WS}/companies?record=${ACME}`,
      workspace(WRITER, { total: 14 }),
    );
    const section = await screen.findByRole("region", {
      name: "Opportunities (14)",
    });
    expect(within(section).getAllByRole("listitem")).toHaveLength(2);
    expect(
      within(section).getByText("Showing the 10 most recently changed of 14."),
    ).toBeInTheDocument();
    expect(
      dealCalls(sent).some((r) => r.path.includes(`company_id=${ACME}`)),
    ).toBe(true);
  });

  it("offers no new deal to a member who may not create one", async () => {
    renderApp(`/w/${WS}/contacts?record=${SAM}`, workspace(READER));
    const section = await screen.findByRole("region", {
      name: "Opportunities (2)",
    });
    expect(within(section).getAllByRole("listitem")).toHaveLength(2);
    expect(
      within(section).queryByRole("button", { name: "New opportunity" }),
    ).toBeNull();
  });
});
