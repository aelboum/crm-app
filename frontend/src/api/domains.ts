import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Custom domains for hosted pages (decision P12-D). Every role sees them;
 * members who may update the workspace add, check and remove them.
 */

export type Domain = components["schemas"]["DomainOut"];

export const domainKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "domains"] as const,
};

export function useDomains(workspaceId: string) {
  return useQuery({
    queryKey: domainKeys.all(workspaceId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/domains", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: domainKeys.all(workspaceId) });
}

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  domain_id: id,
});

export function useAddDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Domain, ApiError, { hostname: string }>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/domains", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useCheckDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Domain, ApiError, { id: string; version: number }>({
    mutationFn: async ({ id, version }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/domains/{domain_id}/check", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useRemoveDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/domains/{domain_id}", {
            params: { path: one(workspaceId, id) },
          })
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
