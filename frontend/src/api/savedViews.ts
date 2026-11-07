import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Saved views of the contacts list (decision P3-SV): a member's own named
 * filters. Nobody else sees them.
 */

export type ContactView = components["schemas"]["ContactViewOut"];
export type ContactViewFilters = components["schemas"]["ContactViewFilters"];

const key = (workspaceId: string) =>
  ["workspace", workspaceId, "saved-views", "contacts"] as const;

export function useContactViews(workspaceId: string) {
  return useQuery({
    queryKey: key(workspaceId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/saved-views/contacts", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: key(workspaceId) });
}

export function useSaveContactView(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    ContactView,
    ApiError,
    { name: string; filters: ContactViewFilters }
  >({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/saved-views/contacts", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useDeleteContactView(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/saved-views/contacts/{view_id}",
            { params: { path: { tenant_id: workspaceId, view_id: id } } },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

export type DealView = components["schemas"]["DealViewOut"];
export type DealViewFilters = components["schemas"]["DealViewFilters"];

const dealKey = (workspaceId: string) =>
  ["workspace", workspaceId, "saved-views", "opportunities"] as const;

export function useDealViews(workspaceId: string) {
  return useQuery({
    queryKey: dealKey(workspaceId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/saved-views/opportunities", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

export function useSaveDealView(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<
    DealView,
    ApiError,
    { name: string; filters: DealViewFilters }
  >({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/saved-views/opportunities", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: dealKey(workspaceId) }),
  });
}

export function useDeleteDealView(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/saved-views/opportunities/{view_id}",
            { params: { path: { tenant_id: workspaceId, view_id: id } } },
          )
        ).response,
      ),
    onSettled: () =>
      client.invalidateQueries({ queryKey: dealKey(workspaceId) }),
  });
}
