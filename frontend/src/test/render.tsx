import { createMemoryHistory } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import axe from "axe-core";
import { vi } from "vitest";

import { App, createQueryClient } from "../App";
import { createAppRouter } from "../router";

export interface Sent {
  method: string;
  path: string;
  body: unknown;
}

interface Reply {
  status: number;
  body?: unknown;
}
export type Handler = (method: string, path: string, body: unknown) => Reply | undefined;

const json = ({ status, body }: Reply) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

/** Renders the whole app at `path` (under /app) with `fetch` answered by `handler`. */
export function renderApp(path: string, handler: Handler) {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const url = new URL(request.url, "http://localhost");
      const text = await request.text();
      const body: unknown = text ? JSON.parse(text) : undefined;
      const where = url.pathname + url.search;
      sent.push({ method: request.method, path: where, body });
      return json(
        handler(request.method, where, body) ?? { status: 404, body: { detail: "Not Found" } },
      );
    }),
  );
  const router = createAppRouter(createMemoryHistory({ initialEntries: [`/app${path}`] }));
  const view = render(<App router={router} queryClient={createQueryClient()} />);
  return { ...view, sent, router };
}

/** axe violations in the rendered document, as `id: help` strings. */
export async function accessibilityViolations(): Promise<string[]> {
  const result = await axe.run(document.body, {
    // jsdom does not lay out or paint, so contrast cannot be measured here.
    rules: { "color-contrast": { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.help}`);
}
