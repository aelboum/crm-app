import { api } from "./client";

/** Where to go after signing out; never fails. Started together with the
 *  sign-out itself, so the two requests do not wait for each other. */
export async function signOutTarget(): Promise<string> {
  try {
    const result = await api.GET("/v1/sign-out-url");
    if (result.data?.url) return result.data.url;
  } catch {
    // Unreachable server: the application session has already ended.
  }
  return "/app";
}

/** Replaced in tests: jsdom does not navigate. */
export const signOutNavigation = {
  go(url: string): void {
    window.location.assign(url);
  },
};

/**
 * After the application's sign-out: send the browser to the identity
 * provider's end-session address (`GET /v1/sign-out-url`), so the provider's
 * session ends too; the provider then returns straight to `/auth/login`, a
 * new sign-in that asks for a password again (decision P2-G.1). Without one,
 * reload the start page, which also drops everything held in memory and
 * waits for a click (signInRedirect.ts).
 */
export async function leaveAfterSignOut(
  go: (url: string) => void = (url) => {
    signOutNavigation.go(url);
  },
  target: Promise<string> = signOutTarget(),
): Promise<void> {
  go(await target);
}
