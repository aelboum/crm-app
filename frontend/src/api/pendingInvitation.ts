/*
 * An invitation link opened while signed out survives the sign-in round trip
 * in this tab only (sign-in always lands on /app; decisions Q4, Q5). It is
 * removed once used, and on sign-out.
 */
const PENDING = "crm.pendingInvitation";

export interface PendingInvitation {
  workspaceId: string;
  token: string;
}

export function rememberInvitation(pending: PendingInvitation): void {
  try {
    sessionStorage.setItem(PENDING, JSON.stringify(pending));
  } catch {
    // Storage unavailable: the person opens the link again after signing in.
  }
}

export function pendingInvitation(): PendingInvitation | null {
  try {
    const raw = sessionStorage.getItem(PENDING);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (
      typeof value === "object" &&
      value !== null &&
      "workspaceId" in value &&
      "token" in value &&
      typeof value.workspaceId === "string" &&
      typeof value.token === "string"
    ) {
      return { workspaceId: value.workspaceId, token: value.token };
    }
    return null;
  } catch {
    return null;
  }
}

export function forgetInvitation(): void {
  try {
    sessionStorage.removeItem(PENDING);
  } catch {
    // Nothing to remove.
  }
}
