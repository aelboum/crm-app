import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Workspace = components["schemas"]["Workspace"];
export type Member = components["schemas"]["Member"];
export type MemberPage = components["schemas"]["MemberPage"];
export type Access = components["schemas"]["Access"];
export type Role = components["schemas"]["Role"];

export const ROLES: readonly Role[] = ["Owner", "Admin", "Member", "Read-only"];

// Same origin as the API (crm_app.api.spa): the session cookie is sent by
// the browser, and the browser's Origin header satisfies the API's
// same-origin check on changes. `fetch` is looked up per call so tests can
// replace it.
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  credentials: "same-origin",
  fetch: (request) => globalThis.fetch(request),
});

/** A refused or failed API call. `code` is the API's refusal code when it sent one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;

  constructor(status: number, code?: string) {
    super(code ? `API ${status}: ${code}` : `API ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function refusalCode(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
  const detail = body.detail;
  if (typeof detail === "object" && detail !== null && "code" in detail) {
    return typeof detail.code === "string" ? detail.code : undefined;
  }
  return undefined;
}

/** The data of a successful call, or an ApiError carrying the status and refusal code. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  throw new ApiError(result.response.status, refusalCode(result.error));
}
