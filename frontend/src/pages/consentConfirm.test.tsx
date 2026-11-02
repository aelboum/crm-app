import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { accessibilityViolations, renderApp } from "../test/render";

/*
 * Confirming consent from an email link (decision P7-V): nothing is sent
 * until the person presses the button (an email scanner opening the link
 * confirms nothing); the token goes in the request body, never the URL path;
 * an unknown or expired link says so.
 */

const WS = "11111111-2222-4333-8444-555555555555";
const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde";

describe("consent confirmation page", () => {
  it("confirms only when the person presses the button", async () => {
    const user = userEvent.setup();
    const { sent } = renderApp(`/c/${WS}#${TOKEN}`, (method, path) =>
      method === "POST" && path === `/v1/public/consent/${WS}/confirm`
        ? { status: 204 }
        : undefined,
    );
    await screen.findByRole("heading", {
      name: "Confirm your email preferences",
    });
    expect(sent.filter((r) => r.method === "POST")).toHaveLength(0);
    expect(await accessibilityViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Yes, this was me" }));
    expect(await screen.findByText(/your choice is recorded/)).toHaveAttribute(
      "role",
      "status",
    );
    const post = sent.find((r) => r.method === "POST");
    expect(post?.body).toEqual({ token: TOKEN });
    expect(post?.path).not.toContain(TOKEN);
  });

  it("says when the link is no longer valid", async () => {
    const user = userEvent.setup();
    renderApp(`/c/${WS}#${TOKEN}`, (method) =>
      method === "POST"
        ? { status: 404, body: { detail: "Not Found" } }
        : undefined,
    );
    await user.click(
      await screen.findByRole("button", { name: "Yes, this was me" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing was changed",
    );
  });
});
