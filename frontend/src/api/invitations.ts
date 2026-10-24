import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ApiError, unwrap } from "./client";
import { keys as workspaceKeys } from "./queries";
import type { components } from "./schema";

/*
 * Invitations (PHASE2-PLAN.md §8.2; decisions Q4, Q5, P2-F). Creating one in
 * manual mode returns its link once; nothing else ever does, and the link
 * is never cached by this client beyond the dialog that shows it.
 */

export type Invitation = components["schemas"]["InvitationOut"];
export type InvitationRole = components["schemas"]["InvitationIn"]["role"];
export type CreatedInvitation = components["schemas"]["CreatedInvitation"];

const invitationsKey = (workspaceId: string) => [...workspaceKeys.workspace(workspaceId), "invitations"] as const;
const where = (workspaceId: string) => ({ params: { path: { tenant_id: workspaceId } } });

export function useInvitations(workspaceId: string, enabled: boolean) {
  return useQuery({
    queryKey: invitationsKey(workspaceId),
    enabled,
    queryFn: async () => unwrap(await api.GET("/v1/workspaces/{tenant_id}/invitations", where(workspaceId))),
  });
}

export function useCreateInvitation(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<CreatedInvitation, ApiError, { email: string; role: InvitationRole }>({
    mutationFn: async (body) =>
      unwrap(await api.POST("/v1/workspaces/{tenant_id}/invitations", { ...where(workspaceId), body })),
    onSettled: () => client.invalidateQueries({ queryKey: invitationsKey(workspaceId) }),
  });
}

export function useRevokeInvitation(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<Invitation, ApiError, { invitationId: string }>({
    mutationFn: async ({ invitationId }) =>
      unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/invitations/{invitation_id}/revoke", {
          params: { path: { tenant_id: workspaceId, invitation_id: invitationId } },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: invitationsKey(workspaceId) }),
  });
}

/** SaaS-OS's acceptance route: the signed-in invitee redeems the token. */
export function useAcceptInvitation() {
  return useMutation<unknown, ApiError, { workspaceId: string; token: string }>({
    mutationFn: async ({ workspaceId, token }) =>
      unwrap(
        await api.POST("/v1/tenants/{tenant_id}/invitations/accept", {
          params: { path: { tenant_id: workspaceId } },
          body: { token },
        }),
      ),
  });
}

// A link opened while signed out survives the sign-in round trip in this
// tab only (sign-in always lands on /app). It is removed once used.
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
