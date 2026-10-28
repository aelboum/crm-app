import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, type Handler, renderApp } from "../test/render";

/*
 * Forms (decision P7-A): the list, creating a form with the starter fields
 * and an idempotency key, editing and publishing with the form's version,
 * what a Read-only member sees, and the hosted page: what it sends
 * (answers, consent, the empty honeypot, an idempotency key), the thank-you
 * message, refusals shown next to their fields, and an unavailable form.
 * The server enforces every rule.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const FORM_ID = "f1000000-0000-4000-8000-000000000001";
const KEY = "l15C1NiaYj-muzjcZJlhjg";
const stamp = "2026-10-28T09:30:00+00:00";

const FIELDS = [
  { key: "first_name", type: "text", label: "First name", required: true, target: "first_name", options: null },
  { key: "email", type: "email", label: "Email", required: true, target: "email", options: null },
  { key: "topic", type: "select", label: "Topic", required: false, target: null, options: ["Sales", "Support"] },
];

function form(extra: Record<string, unknown> = {}) {
  return {
    id: FORM_ID,
    name: "Contact us",
    status: "draft",
    public_key: KEY,
    fields: FIELDS,
    tag_id: null,
    tag: null,
    thank_you: "Thanks! We will be in touch soon.",
    consent_text: "Email me about my enquiry.",
    contact_owner_user_id: "u-me",
    submission_count: 2,
    last_submission_at: stamp,
    created_at: stamp,
    updated_at: stamp,
    created_by_user_id: "u-me",
    updated_by_user_id: "u-me",
    version: 3,
    ...extra,
  };
}

const SUBMISSIONS = {
  items: [
    {
      id: "s2",
      answers: { first_name: "Sam", email: "sam@example.test", topic: "Sales" },
      outcome: "matched",
      consent: false,
      created_at: stamp,
      contact_id: "c1",
      contact: { id: "c1", name: "Sam Jansen", archived: false },
    },
  ],
  next_cursor: null,
  total: 1,
  total_capped: false,
};

type Reply = { status: number; body?: unknown } | undefined;

function workspace(
  actions: Record<string, boolean>,
  onWrite?: (method: string, path: string, body: unknown) => Reply,
): Handler {
  return (method, path, body) => {
    const base = `/v1/workspaces/${WS}`;
    if (path === "/auth/me") return { status: 200, body: { user_id: "u-me" } };
    if (path === base) return { status: 200, body: { id: WS, name: "Acme", status: "active" } };
    if (path === `${base}/access`) {
      return { status: 200, body: { membership_id: "m1", roles: ["Owner"], actions } };
    }
    if (path.startsWith(`${base}/members?`)) {
      return { status: 200, body: { items: [], total: 0, limit: 50, offset: 0 } };
    }
    if (path === `${base}/tags`) {
      return { status: 200, body: { items: [{ id: "t1", name: "Web lead", version: 1 }] } };
    }
    if (method === "GET" && path === `${base}/forms`) {
      return { status: 200, body: { items: [form({ status: "published" }), form({ id: "f2", name: "Newsletter" })] } };
    }
    if (method === "GET" && path === `${base}/forms/${FORM_ID}`) return { status: 200, body: form() };
    if (method === "GET" && path.startsWith(`${base}/forms/${FORM_ID}/submissions`)) {
      return { status: 200, body: SUBMISSIONS };
    }
    if (method !== "GET" && path.startsWith(`${base}/forms`)) return onWrite?.(method, path, body);
    return undefined;
  };
}

const MANAGER = { read_members: true, read_forms: true, manage_forms: true };
const READER = { read_members: true, read_forms: true, manage_forms: false };

describe("forms page", () => {
  it("lists the forms with their status and submissions", async () => {
    renderApp(`/w/${WS}/forms`, workspace(MANAGER));
    const card = await screen.findByRole("button", { name: /Newsletter/ });
    expect(card).toHaveTextContent("Draft");
    expect(screen.getByRole("button", { name: /Contact us/ })).toHaveTextContent("Published");
    expect(screen.getByRole("button", { name: /Contact us/ })).toHaveTextContent("3 fields");
    expect(screen.getByRole("button", { name: "New form" })).toBeInTheDocument();
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("creates a form with the starter fields and an idempotency key", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/forms`,
      workspace(MANAGER, (method) => (method === "POST" ? { status: 201, body: form() } : undefined)),
    );
    await user.click(await screen.findByRole("button", { name: "New form" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
    });
    const post = sent.find((r) => r.method === "POST");
    expect(post?.body).toMatchObject({
      name: "Untitled form",
      fields: [
        { key: "first_name", target: "first_name", required: true },
        { key: "email", target: "email", required: true },
        { key: "phone", target: "phone", required: false },
      ],
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    expect(await screen.findByRole("heading", { name: "Preview" })).toBeInTheDocument();
  });

  it("saves only what changed and publishes with the form's version", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/w/${WS}/forms?record=${FORM_ID}`,
      workspace(MANAGER, (method) => (method === "PATCH" ? { status: 200, body: form({ version: 4 }) } : undefined)),
    );
    const name = await screen.findByLabelText("Form name");
    await user.clear(name);
    await user.type(name, "Get a quote");
    await user.click(screen.getByRole("button", { name: "Move Email down" }));
    await user.click(screen.getByRole("button", { name: "Save and publish" }));
    await waitFor(() => {
      expect(sent.filter((r) => r.method === "PATCH")).toHaveLength(1);
    });
    const patch = sent.find((r) => r.method === "PATCH")?.body as { fields: { key: string }[] };
    expect(patch).toMatchObject({ name: "Get a quote", status: "published" });
    expect(patch.fields.map((field) => field.key)).toEqual(["first_name", "topic", "email"]);
    expect(Object.keys(patch).sort()).toEqual(["fields", "name", "status"]);
    expect(headersSent.find((r) => r.method === "PATCH")?.headers["if-match"]).toBe('"3"');
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("explains a publishing refusal", async () => {
    const user = userEvent.setup();
    renderApp(
      `/w/${WS}/forms?record=${FORM_ID}`,
      workspace(MANAGER, () => ({ status: 422, body: { detail: { code: "first_name_field_required" } } })),
    );
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs a required field that fills First name");
  });

  it("adds a dropdown with two options and shows its settings", async () => {
    const user = userEvent.setup();
    renderApp(`/w/${WS}/forms?record=${FORM_ID}`, workspace(MANAGER));
    await user.click(await screen.findByRole("button", { name: "Add field: Dropdown" }));
    const settings = screen.getByRole("group", { name: "Settings of Dropdown" });
    expect(within(settings).getByLabelText("Options")).toHaveValue("Option 1\nOption 2");
    expect(screen.getByText("Unsaved changes.")).toBeInTheDocument();
  });

  it("shows submissions with their outcome and answers", async () => {
    renderApp(`/w/${WS}/forms?record=${FORM_ID}`, workspace(MANAGER));
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("button", { name: "Sam Jansen" })).toBeInTheDocument();
    expect(within(table).getByText("Matched")).toBeInTheDocument();
    expect(within(table).getByText(/sam@example.test/)).toBeInTheDocument();
  });

  it("offers a Read-only member the form without changes", async () => {
    renderApp(`/w/${WS}/forms?record=${FORM_ID}`, workspace(READER));
    expect(await screen.findByRole("heading", { level: 1, name: "Contact us" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete form" })).toBeNull();
    expect(screen.getByLabelText("Thank-you message")).toBeDisabled();
  });
});

const PUBLIC = `/v1/public/forms/${WS}/${KEY}`;

function visitor(onSubmit: (body: unknown) => Reply, page?: Reply): Handler {
  return (method, path, body) => {
    if (path === PUBLIC && method === "GET") {
      return (
        page ?? {
          status: 200,
          body: {
            name: "Contact us",
            fields: FIELDS.map(({ key, type, label, required, options }) => ({ key, type, label, required, options })),
            consent_text: "Email me about my enquiry.",
            thank_you: "Thanks! We will be in touch soon.",
          },
        }
      );
    }
    if (path === PUBLIC && method === "POST") return onSubmit(body);
    return undefined;
  };
}

describe("hosted form page", () => {
  it("sends the answers, consent, an empty honeypot and an idempotency key", async () => {
    const user = userEvent.setup();
    const { sent, headersSent } = renderApp(
      `/f/${WS}/${KEY}`,
      visitor(() => ({ status: 201, body: { thank_you: "Thanks! We will be in touch soon." } })),
    );
    await user.type(await screen.findByRole("textbox", { name: "First name" }), "Sam");
    await user.type(screen.getByRole("textbox", { name: "Email" }), "sam@example.test");
    await user.selectOptions(screen.getByLabelText("Topic"), "Sales");
    await user.click(screen.getByLabelText("Email me about my enquiry."));
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("Thanks! We will be in touch soon.")).toBeInTheDocument();
    const post = sent.find((r) => r.method === "POST");
    expect(post?.body).toEqual({
      answers: { first_name: "Sam", email: "sam@example.test", topic: "Sales" },
      consent: true,
      website: "",
    });
    expect(headersSent.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f]{32}$/);
    expect(sent.some((r) => r.path === "/auth/me")).toBe(false);
  });

  it("shows refusals next to their fields", async () => {
    const user = userEvent.setup();
    renderApp(
      `/f/${WS}/${KEY}`,
      visitor(() => ({
        status: 422,
        body: { detail: { code: "invalid_answers", fields: { first_name: "required", email: "invalid" } } },
      })),
    );
    await user.click(await screen.findByRole("button", { name: "Submit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Some answers need attention.");
    expect(screen.getByRole("textbox", { name: "First name" })).toHaveAccessibleDescription("This field is required.");
    expect(screen.getByRole("textbox", { name: "Email" })).toHaveAccessibleDescription("Check this answer.");
    // A corrected field no longer shows the old message; the others still do.
    await user.type(screen.getByRole("textbox", { name: "First name" }), "Sam");
    expect(screen.getByRole("textbox", { name: "First name" })).not.toHaveAccessibleDescription();
    expect(screen.getByRole("textbox", { name: "Email" })).toHaveAccessibleDescription("Check this answer.");
  });

  it("says when a form is not available", async () => {
    renderApp(`/f/${WS}/${KEY}`, visitor(() => undefined, { status: 404, body: { detail: "Not Found" } }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This form is not available.");
  });
});
