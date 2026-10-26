import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

/*
 * Self-service signup (decision S-1; SIGNUP-PLAN.md §4, Stage D). The
 * backend's kill switch is authoritative: the status flag only decides what
 * to offer, and every signup call can still answer 404 when signup is off.
 * The signup routes answer with SaaS-OS's plain-text `detail` (for example
 * "workspace_limit_reached"), not the `{code}` object other routes use.
 */

export type Signup = components["schemas"]["SignupOut"];
export type SignupState = Signup["state"];

export const OPEN_STATES: readonly SignupState[] = ["started", "provisioning"];

export const signupKeys = {
  status: ["signup", "status"] as const,
};

export type SignupAvailability = "loading" | "on" | "off" | "unknown";

/** Whether signup is offered, from the server's flag. "unknown" (the check
 *  failed) never means "off": the caller must not say signup is off. */
export async function signupEnabled(): Promise<boolean> {
  const result = await api.GET("/v1/signups/status");
  if (!result.response.ok || !result.data) throw new SignupError(result.response.status, undefined, null);
  return result.data.enabled;
}

export function useSignupStatus(): SignupAvailability {
  const status = useQuery({
    queryKey: signupKeys.status,
    queryFn: signupEnabled,
    retry: false,
    staleTime: 60_000,
  });
  if (status.isPending) return "loading";
  if (status.isError) return "unknown";
  return status.data ? "on" : "off";
}

/** A refused or failed signup call. `reason` is the API's plain-text code,
 *  `retryAfter` the seconds the server asked to wait (429, 503). */
export class SignupError extends Error {
  readonly status: number;
  readonly reason: string | undefined;
  readonly retryAfter: number | null;

  constructor(status: number, reason: string | undefined, retryAfter: number | null) {
    super(reason ? `signup ${status}: ${reason}` : `signup ${status}`);
    this.name = "SignupError";
    this.status = status;
    this.reason = reason;
    this.retryAfter = retryAfter;
  }
}

/** Status 0: the request never reached the server. */
export const NETWORK = 0;

function reasonOf(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
  const detail = body.detail;
  // Codes are snake_case; human messages ("Not authorized.") are not codes.
  return typeof detail === "string" && /^[a-z_]+$/.test(detail) ? detail : undefined;
}

function retryAfterOf(response: Response): number | null {
  const raw = response.headers.get("Retry-After");
  if (raw === null) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

async function call<T>(
  request: () => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await request();
  } catch {
    throw new SignupError(NETWORK, undefined, null);
  }
  if (result.response.ok && result.data !== undefined) return result.data;
  throw new SignupError(result.response.status, reasonOf(result.error), retryAfterOf(result.response));
}

/** `POST /v1/signups`: 201 complete, 202 still provisioning, 200 a replay of
 *  the same key or another unfinished signup. The state, not the status,
 *  says what happened. */
export async function startSignup(idempotencyKey: string, workspaceName: string): Promise<Signup> {
  return call(() =>
    api.POST("/v1/signups", {
      params: { header: { "Idempotency-Key": idempotencyKey } },
      body: { workspace_name: workspaceName },
    }),
  );
}

/** `GET /v1/signups/current`: the unfinished signup, else the latest; `null`
 *  when the person has none (404, also the answer while signup is off). */
export async function currentSignup(): Promise<Signup | null> {
  try {
    return await call(() => api.GET("/v1/signups/current"));
  } catch (error) {
    if (error instanceof SignupError && error.status === 404) return null;
    throw error;
  }
}

/*
 * The workspace name, checked as the backend does
 * (crm_app.domains.signup.normalize_workspace_name): NFC, inner whitespace
 * collapsed, 1 to 100 characters, no control, format or other non-printing
 * characters. The backend stays authoritative.
 */
export const NAME_MAX = 100;

export type NameProblem = "empty" | "long" | "character";

export function normalizeWorkspaceName(value: string): string {
  return value.normalize("NFC").split(/\s+/u).filter(Boolean).join(" ");
}

export function workspaceNameProblem(value: string): NameProblem | null {
  const name = normalizeWorkspaceName(value);
  if (!name) return "empty";
  // Code points, as Python counts them; the backend is the reference.
  if (Array.from(name).length > NAME_MAX) return "long";
  if (/\p{C}/u.test(name)) return "character";
  return null;
}

/*
 * One idempotency key per signup attempt, kept in this tab with the name it
 * was sent with, so a retry after a failure or a reload repeats the same
 * attempt. A new key is made only for a genuinely new attempt: another name,
 * or a fresh start after a failed or expired signup.
 */
const ATTEMPT = "crm.signupAttempt";

export interface SignupAttempt {
  key: string;
  name: string;
}

// The same attempt when sessionStorage is unavailable, for this page's life.
let inMemory: SignupAttempt | null = null;

export function attemptFor(name: string): SignupAttempt {
  const kept = keptAttempt();
  if (kept?.name === name) return kept;
  const attempt = { key: crypto.randomUUID(), name };
  inMemory = attempt;
  try {
    sessionStorage.setItem(ATTEMPT, JSON.stringify(attempt));
  } catch {
    // Storage unavailable: the key lives only as long as this page.
  }
  return attempt;
}

export function keptAttempt(): SignupAttempt | null {
  try {
    const raw = sessionStorage.getItem(ATTEMPT);
    if (!raw) return inMemory;
    const value: unknown = JSON.parse(raw);
    if (
      typeof value === "object" &&
      value !== null &&
      "key" in value &&
      "name" in value &&
      typeof value.key === "string" &&
      typeof value.name === "string"
    ) {
      return { key: value.key, name: value.name };
    }
    return null;
  } catch {
    return inMemory;
  }
}

export function forgetAttempt(): void {
  inMemory = null;
  try {
    sessionStorage.removeItem(ATTEMPT);
  } catch {
    // Nothing to remove.
  }
}
