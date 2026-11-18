import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  accessibilityViolations,
  type Handler,
  renderApp,
} from "../test/render";

/*
 * Settings › AI (decision P9-S): AI, the contact brief and a model are
 * switched on with the right requests; a model the workspace's
 * preferences rule out cannot be chosen and says why; preferences and the
 * monthly cap are saved; members without the permission see no settings.
 * AI usage (decision P9-U) comes from SaaS-OS's own read routes: by
 * feature this month and by month, or a plain note when there is none.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const URL = `/w/${WS}/settings?section=ai`;

const MODEL = {
  provider_key: "groq",
  model_id: "openai/gpt-oss-20b",
  lifecycle: "active",
  granted: false,
  rank: null,
  eligible: false,
  blocked_by: ["tenant_ai_disabled", "use_case_not_granted"],
};
const BLOCKED = {
  ...MODEL,
  provider_key: "other",
  model_id: "big-model",
  blocked_by: ["training_use"],
};

const SETTINGS = {
  enabled: false,
  features: [{ feature: "contact_brief", enabled: false }],
  preferences: {
    allowed_residency: [],
    max_retention_days: null,
    exclude_training_use: false,
  },
  models: [{ feature: "contact_brief", models: [MODEL, BLOCKED] }],
};

const BUDGET = {
  state: "ok",
  currency: "EUR",
  limit: "25",
  source: "tenant_cap",
  settled: "3.5",
  reserved: "0",
  retained: "0",
  remaining: "21.5",
  period_start: "2026-11-01T00:00:00Z",
  warn_thresholds: [80],
  threshold_reached: null,
};

function amounts(attempts: number, cost: string | null) {
  return {
    attempts,
    attempts_by_state: [],
    input_tokens: attempts * 1000,
    output_tokens: attempts * 200,
    cached_input_tokens: 0,
    tokens_by_provenance: [],
    estimated_cost: cost ? [{ currency: "EUR", estimated: cost }] : [],
    usage_unknown_attempts: 0,
    cost_unknown_attempts: 0,
  };
}

function usage(used: boolean) {
  const window = {
    tenant_id: WS,
    since: "2025-12-01T00:00:00Z",
    until: "2026-12-01T00:00:00Z",
    timezone: "UTC",
    basis: "x",
  };
  const months = ["2026-10", "2026-11"].map((key, index) => ({
    key,
    amounts: used ? amounts(index + 2, `0.0${index + 1}`) : amounts(0, null),
  }));
  return {
    monthly: {
      ...window,
      group_by: "month",
      totals: used ? amounts(5, "0.03") : amounts(0, null),
      groups: months,
    },
    byFeature: {
      ...window,
      group_by: "use_case",
      totals: used ? amounts(3, "0.02") : amounts(0, null),
      groups: used
        ? [{ key: "crm.contact_brief", amounts: amounts(3, "0.02") }]
        : [],
      token_quota: {
        state: "unconfigured",
        limit: null,
        used: null,
        remaining: null,
        basis: "x",
      },
      budget: { ...BUDGET, basis: "x" },
    },
  };
}

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  allowed: boolean,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
  used = false,
): Handler {
  const reads = usage(used);
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    const tenant = `/v1/tenants/${WS}/ai`;
    if (method !== "GET")
      return onWrite?.(method, path, body) ?? { status: 204 };
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === base)
      return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return {
        status: 200,
        body: {
          membership_id: "m1",
          roles: [allowed ? "Admin" : "Member"],
          actions: {
            read_ai_settings: allowed,
            manage_ai_settings: allowed,
            read_ai_usage: allowed,
            manage_ai_budget: allowed,
            read_members: true,
          },
        },
      };
    }
    if (path.startsWith(`${base}/members?`)) {
      return {
        status: 200,
        body: { items: [], total: 0, limit: 50, offset: 0 },
      };
    }
    if (path === `${base}/ai`) return { status: 200, body: SETTINGS };
    if (path === `${base}/ai/budget`) return { status: 200, body: BUDGET };
    if (path.startsWith(`${tenant}/usage/monthly?`))
      return { status: 200, body: reads.monthly };
    if (path.startsWith(`${tenant}/usage?`))
      return { status: 200, body: reads.byFeature };
    return undefined;
  };
}

describe("AI settings", () => {
  it("turns AI, the contact brief and a model on", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace(true));
    const card = await screen.findByRole("region", { name: "AI" });
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(
      within(card).getByRole("switch", { name: "Use AI in this workspace" }),
    );
    await user.click(
      within(card).getByRole("switch", { name: "Contact brief" }),
    );
    await user.click(
      within(card).getByRole("switch", { name: "groq · openai/gpt-oss-20b" }),
    );
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "PUT",
        path: `/v1/workspaces/${WS}/ai/enabled`,
        body: { enabled: true },
      });
    });
    expect(sent).toContainEqual({
      method: "PUT",
      path: `/v1/workspaces/${WS}/ai/features/contact_brief`,
      body: { enabled: true },
    });
    expect(sent).toContainEqual({
      method: "PUT",
      path: `/v1/workspaces/${WS}/ai/models`,
      body: {
        feature: "contact_brief",
        provider_key: "groq",
        model_id: "openai/gpt-oss-20b",
        enabled: true,
        rank: 0,
      },
    });
  });

  it("explains why a model cannot be chosen", async () => {
    renderApp(URL, workspace(true));
    const card = await screen.findByRole("region", { name: "AI" });
    const blocked = await within(card).findByRole("switch", {
      name: "other · big-model",
    });
    expect(blocked).toBeDisabled();
    expect(card).toHaveTextContent("May train on your data");
    expect(card).toHaveTextContent("Feature not allowed");
  });

  it("saves preferences and a monthly cap", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(URL, workspace(true));
    const prefs = await screen.findByRole("region", {
      name: "Data preferences",
    });
    await user.click(
      within(prefs).getByLabelText("Never let the provider train on our data"),
    );
    await user.selectOptions(
      within(prefs).getByLabelText(
        "Longest time the provider may keep our data",
      ),
      "0",
    );
    await user.type(
      within(prefs).getByLabelText("Allowed data locations"),
      "EU",
    );
    await user.click(
      within(prefs).getByRole("button", { name: "Save preferences" }),
    );
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "PUT",
        path: `/v1/workspaces/${WS}/ai/preferences`,
        body: {
          exclude_training_use: true,
          max_retention_days: 0,
          allowed_residency: ["eu"],
        },
      });
    });

    const budget = screen.getByRole("region", { name: "Monthly AI budget" });
    expect(await within(budget).findByText("21.5 EUR")).toBeInTheDocument();
    expect(budget).toHaveTextContent("Within budget");
    await user.type(within(budget).getByLabelText("Monthly cap"), "10.50");
    await user.click(within(budget).getByRole("button", { name: "Set cap" }));
    await waitFor(() => {
      expect(sent).toContainEqual({
        method: "PUT",
        path: `/v1/workspaces/${WS}/ai/budget`,
        body: { currency: "EUR", amount: "10.50" },
      });
    });
  });

  it("shows a refusal without provider detail", async () => {
    const user = userEvent.setup();
    renderApp(
      URL,
      workspace(true, (_method, path) =>
        path.endsWith("/ai/models")
          ? { status: 404, body: { detail: { code: "unknown_model" } } }
          : undefined,
      ),
    );
    const card = await screen.findByRole("region", { name: "AI" });
    await user.click(
      await within(card).findByRole("switch", {
        name: "groq · openai/gpt-oss-20b",
      }),
    );
    expect(await within(card).findByRole("alert")).toHaveTextContent(
      "That model is no longer available.",
    );
  });

  it("says when the workspace has used no AI", async () => {
    renderApp(URL, workspace(true));
    const card = await screen.findByRole("region", { name: "AI usage" });
    expect(await within(card).findByText("No AI use yet.")).toBeInTheDocument();
    expect(within(card).queryByRole("table")).toBeNull();
  });

  it("shows AI usage by feature and by month", async () => {
    const { sent } = renderApp(URL, workspace(true, undefined, true));
    const card = await screen.findByRole("region", { name: "AI usage" });
    const feature = await within(card).findByRole("table", {
      name: "This month, by feature",
    });
    const brief = within(feature).getByRole("row", { name: /Contact brief/ });
    expect(brief).toHaveTextContent("3");
    expect(brief).toHaveTextContent("3,600");
    expect(brief).toHaveTextContent("0.02 EUR");
    const months = within(card).getByRole("table", {
      name: "The last 12 months",
    });
    const rows = within(months).getAllByRole("row");
    // Newest first, after the header row.
    expect(rows[1]).toHaveTextContent("November 2026");
    expect(rows[2]).toHaveTextContent("October 2026");
    expect(sent).toContainEqual(
      expect.objectContaining({
        method: "GET",
        path: `/v1/tenants/${WS}/ai/usage?group_by=use_case`,
      }),
    );
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("shows members no settings", async () => {
    const { sent } = renderApp(URL, workspace(false));
    expect(
      await screen.findByText(/Only Owners and Admins can see AI settings/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "AI" })).toBeNull();
    expect(sent.filter((r) => r.path.includes("/ai"))).toEqual([]);
  });
});
