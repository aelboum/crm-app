import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Customer-owned sending domains (decision P6-D). Every role sees them;
 * members who may update the workspace register, verify and remove
 * domains and manage sender identities.
 */

export type SendingDomain = components["schemas"]["SendingDomainOut"];
export type SenderIdentity = components["schemas"]["IdentityOut"];
export type IdentityInput = components["schemas"]["IdentityIn"];

export const sendingDomainKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "sending-domains"] as const,
};

export function useSendingDomains(workspaceId: string) {
  return useQuery({
    queryKey: sendingDomainKeys.all(workspaceId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/sending-domains", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: sendingDomainKeys.all(workspaceId) });
}

export function useRegisterDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<SendingDomain, ApiError, { domain: string }>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/sending-domains", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useVerifyDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<SendingDomain, ApiError, { id: string; version: number }>({
    mutationFn: async ({ id, version }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/sending-domains/{domain_id}/verify",
          {
            params: {
              path: { tenant_id: workspaceId, domain_id: id },
              header: ifMatch(version),
            },
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useRemoveSendingDomain(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/sending-domains/{domain_id}",
            { params: { path: { tenant_id: workspaceId, domain_id: id } } },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

export function useAddIdentity(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    SenderIdentity,
    ApiError,
    { domainId: string; body: IdentityInput }
  >({
    mutationFn: async ({ domainId, body }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/sending-domains/{domain_id}/identities",
          {
            params: { path: { tenant_id: workspaceId, domain_id: domainId } },
            body,
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useRemoveIdentity(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/sender-identities/{identity_id}",
            { params: { path: { tenant_id: workspaceId, identity_id: id } } },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
