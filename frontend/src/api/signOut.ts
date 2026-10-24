import { api } from "./client";

/**
 * After the application's sign-out: send the browser to the identity
 * provider's end-session address (`GET /v1/sign-out-url`), so the provider's
 * session ends too and the next "Sign in" asks for a password again. Without
 * one, reload the start page, which also drops everything held in memory.
 */
export async function leaveAfterSignOut(
  go: (url: string) => void = (url) => {
    window.location.assign(url);
  },
): Promise<void> {
  let target = "/app";
  try {
    const result = await api.GET("/v1/sign-out-url");
    if (result.data?.url) target = result.data.url;
  } catch {
    // Unreachable server: the application session has already ended.
  }
  go(target);
}
