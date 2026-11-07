import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Integrations and their API keys (decision P12-K). Owners and Admins only
 * (`manage_integrations`). An integration is Member or Read-only; a key is
 * shown once, in the response that issues it, and never again.
 */

export type Integration = components["schemas"]["IntegrationOut"];
export type IntegrationKey = components["schemas"]["KeyOut"];
export type IssuedKey = components["schemas"]["IssuedKey"];
export type IntegrationRole = "Member" | "Read-only";
export const EXPIRY_DAYS = [30, 90, 365] as const;
export const MAX_KEYS = 2;

export const integrationKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "integrations"] as const,
};

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  integration_id: id,
});

export function useIntegrations(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: integrationKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/integrations", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: integrationKeys.all(workspaceId) });
}

export function useCreateIntegration(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Integration,
    ApiError,
    { name: string; role: IntegrationRole }
  >({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/integrations", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useDisableIntegration(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Integration, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/integrations/{integration_id}/disable",
          { params: { path: one(workspaceId, id) } },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useIssueKey(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    IssuedKey,
    ApiError,
    { id: string; name: string; expires_in_days: number | null }
  >({
    mutationFn: async ({ id, ...body }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/integrations/{integration_id}/keys",
          { params: { path: one(workspaceId, id) }, body },
        ),
      ),
    onSuccess: () => refresh(),
  });
}

export function useRevokeKey(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string; keyId: string }>({
    mutationFn: async ({ id, keyId }) =>
      expectNoContent(
        (
          await api.POST(
            "/v1/workspaces/{tenant_id}/integrations/{integration_id}/keys/{key_id}/revoke",
            { params: { path: { ...one(workspaceId, id), key_id: keyId } } },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
