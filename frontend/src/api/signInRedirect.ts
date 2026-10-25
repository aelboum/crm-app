/*
 * The start page sends a visitor without a session straight on to the
 * sign-in page (decision S-2), with two exceptions:
 * - after a sign-out in this tab: the identity provider's own session may
 *   still be alive (no end-session address configured) and would sign the
 *   person in again without asking;
 * - when it already did so in the last 10 seconds, so a failing sign-in
 *   cannot bounce the browser back and forth.
 * In both cases, and when storage is unavailable, the sign-in screen stays.
 */
const SIGNED_OUT = "crm.signedOut";
const LAST_REDIRECT = "crm.signInRedirectAt";
const QUIET_MS = 10_000;

export const LOGIN_PATH = "/auth/login";

/** Replaced in tests; `replace` keeps the start page out of the history, so
 *  Back from the sign-in page does not bounce forward again. */
export const signInNavigation = {
  leave(url: string): void {
    window.location.replace(url);
  },
};

export function markSignedOut(): void {
  try {
    sessionStorage.setItem(SIGNED_OUT, "1");
  } catch {
    // Storage unavailable: shouldRedirectToSignIn() never redirects then.
  }
}

export function clearSignedOut(): void {
  try {
    sessionStorage.removeItem(SIGNED_OUT);
  } catch {
    // Nothing to clear.
  }
}

/** Whether to leave for the sign-in page now; records the attempt. */
export function shouldRedirectToSignIn(now: number = Date.now()): boolean {
  try {
    if (sessionStorage.getItem(SIGNED_OUT)) return false;
    const last = Number(sessionStorage.getItem(LAST_REDIRECT));
    if (last && now - last < QUIET_MS) return false;
    sessionStorage.setItem(LAST_REDIRECT, String(now));
    return true;
  } catch {
    return false;
  }
}
