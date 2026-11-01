import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Websites (decision P12-W): the external sites whose pages may submit the
 * workspace's published forms. Members who read forms see them; members
 * who manage forms add, change, disable and remove them.
 */

export type Website = components["schemas"]["WebsiteOut"];

export const websiteKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "websites"] as const,
};

export function useWebsites(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: websiteKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/websites", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: websiteKeys.all(workspaceId) });
}

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  website_id: id,
});

export function useCreateWebsite(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Website, ApiError, { name: string; origins: string[] }>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/websites", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateWebsite(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Website,
    ApiError,
    {
      id: string;
      version: number;
      changes: {
        status?: "active" | "disabled";
        name?: string;
        origins?: string[];
      };
    }
  >({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/websites/{website_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteWebsite(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/websites/{website_id}", {
            params: { path: one(workspaceId, id) },
          })
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
