import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, renderApp } from "../test/render";

/*
 * Unsubscribing from a campaign email's link (decisions P7-C, E-H1):
 * nothing is sent until the person presses the button (an email scanner
 * opening the link unsubscribes no one); an incomplete link sends nothing.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const TOKEN = "0123456789abcdef0123456789abcdef";

describe("unsubscribe page", () => {
  it("unsubscribes only when the person presses the button", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/u/${WS}#${TOKEN}`, (method, path) =>
      method === "POST" && path === `/v1/public/unsubscribe/${WS}/${TOKEN}`
        ? { status: 204 }
        : undefined,
    );
    await screen.findByRole("heading", { name: "Unsubscribe" });
    expect(sent.filter((r) => r.method === "POST")).toHaveLength(0);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Unsubscribe me" }));
    expect(await screen.findByText(/no more marketing email/)).toHaveAttribute(
      "role",
      "status",
    );
    expect(sent.filter((r) => r.method === "POST")).toHaveLength(1);
  });

  it("sends nothing for an incomplete link", async () => {
    const { sent } = renderApp(`/u/${WS}#abc`, () => undefined);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This link is not complete",
    );
    expect(screen.queryByRole("button", { name: "Unsubscribe me" })).toBeNull();
    expect(sent.filter((r) => r.method === "POST")).toHaveLength(0);
  });

  it("says when it did not work", async () => {
    const user = userEvent.setup();
    renderApp(`/u/${WS}#${TOKEN}`, (method) =>
      method === "POST" ? { status: 429, body: { detail: "Too Many" } } : undefined,
    );
    await user.click(
      await screen.findByRole("button", { name: "Unsubscribe me" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again");
  });
});
