import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type Role, unwrap } from "./client";
import { forgetInvitation } from "./pendingInvitation";
import { forgetAttempt } from "./signups";
import { clearSignedOut, markSignedOut } from "./signInRedirect";
import type { components } from "./schema";

export const PAGE_SIZE = 50;

export const keys = {
  me: ["me"] as const,
  settings: (id: string) => ["workspace", id, "settings"] as const,
  directory: ["directory"] as const,
  workspace: (id: string) => ["workspace", id] as const,
  access: (id: string) => ["workspace", id, "access"] as const,
  members: (id: string, offset: number) => ["workspace", id, "members", offset] as const,
};

/** The signed-in user, or null when there is no valid session. */
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      const result = await api.GET("/auth/me");
      if (result.response.status === 401) return null;
      const me = unwrap(result);
      // Signed in again, however it happened: a later expiry may redirect.
      clearSignedOut();
      return me;
    },
  });
}

/** The caller's workspaces (decision P2-F 2). Listing grants nothing: each
 *  workspace is still authorized on its own when opened. */
export function useDirectory(enabled = true) {
  return useQuery({
    queryKey: keys.directory,
    enabled,
    queryFn: async () => unwrap(await api.GET("/v1/workspaces")),
  });
}

const path = (workspaceId: string) => ({ params: { path: { tenant_id: workspaceId } } });

export function useWorkspace(workspaceId: string) {
  return useQuery({
    queryKey: keys.workspace(workspaceId),
    queryFn: async () => unwrap(await api.GET("/v1/workspaces/{tenant_id}", path(workspaceId))),
  });
}

export function useAccess(workspaceId: string) {
  return useQuery({
    queryKey: keys.access(workspaceId),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/access", path(workspaceId))),
  });
}

export function useMembers(workspaceId: string, offset: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.members(workspaceId, offset),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/members", {
          params: { path: { tenant_id: workspaceId }, query: { limit: PAGE_SIZE, offset } },
        }),
      ),
  });
}

export type MemberChange =
  | { kind: "assign_role"; role: Role }
  | { kind: "remove_role"; role: Role }
  | { kind: "suspend" | "reactivate" | "revoke" };

export interface ChangeRequest {
  membershipId: string;
  change: MemberChange;
  confirmOwnerChange: boolean;
}

async function send(workspaceId: string, { membershipId, change, confirmOwnerChange }: ChangeRequest) {
  const where = { tenant_id: workspaceId, membership_id: membershipId };
  const confirm = { confirm_owner_change: confirmOwnerChange };
  switch (change.kind) {
    case "assign_role":
      return unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/members/{membership_id}/roles", {
          params: { path: where },
          body: { role: change.role, ...confirm },
        }),
      );
    case "remove_role":
      return unwrap(
        await api.DELETE("/v1/workspaces/{tenant_id}/members/{membership_id}/roles/{role}", {
          params: { path: { ...where, role: change.role }, query: confirm },
        }),
      );
    case "suspend":
      return unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/members/{membership_id}/suspend", {
          params: { path: where },
          body: confirm,
        }),
      );
    case "reactivate":
      return unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/members/{membership_id}/reactivate", {
          params: { path: where },
          body: confirm,
        }),
      );
    case "revoke":
      return unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/members/{membership_id}/revoke", {
          params: { path: where },
          body: confirm,
        }),
      );
  }
}

/** Applies one membership change; on success or refusal, re-reads the workspace's members and access. */
export function useMemberChange(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<unknown, ApiError, ChangeRequest>({
    mutationFn: (request) => send(workspaceId, request),
    onSettled: () => client.invalidateQueries({ queryKey: keys.workspace(workspaceId) }),
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return useMutation<null, ApiError>({
    mutationFn: async () => {
      const result = await api.POST("/auth/logout");
      if (!result.response.ok) throw new ApiError(result.response.status);
      return null;
    },
    onSuccess: () => {
      client.clear();
      client.setQueryData(keys.me, null);
      forgetInvitation();
      forgetAttempt();
      markSignedOut();
    },
  });
}

export type WorkspaceSettings = components["schemas"]["SettingsOut"];
export type WorkspaceSettingsUpdate = components["schemas"]["SettingsUpdate"];

/** Locale, time zone and currency (decision P2-F 1); version 0 is the defaults. */
export function useWorkspaceSettings(workspaceId: string) {
  return useQuery({
    queryKey: keys.settings(workspaceId),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/settings", path(workspaceId))),
  });
}

export function useSaveWorkspaceSettings(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<WorkspaceSettings, ApiError, { version: number; changes: WorkspaceSettingsUpdate }>({
    mutationFn: async ({ version, changes }) =>
      unwrap(
        await api.PATCH("/v1/workspaces/{tenant_id}/settings", {
          params: { path: { tenant_id: workspaceId }, header: { "If-Match": `"${String(version)}"` } },
          body: changes,
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: keys.settings(workspaceId) }),
  });
}
