import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, useRefresh, where } from "./records";
import type { components } from "./schema";

/*
 * The workspace's tag vocabulary (decision P3-C). Every role reads it;
 * Owners and Admins create, rename and delete tags (`update_workspace` in
 * `/access`). Renaming or deleting a tag changes what records show, so both
 * kinds of record are re-read afterwards.
 */

export type Tag = components["schemas"]["TagOut"];
export type TagRef = components["schemas"]["TagRef"];

export const tagKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "tags"] as const,
};

export function useTags(workspaceId: string) {
  return useQuery({
    queryKey: tagKeys.all(workspaceId),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/tags", { params: { path: where(workspaceId) } })),
  });
}

function useAfterChange(workspaceId: string, records: boolean) {
  const client = useQueryClient();
  const refresh = useRefresh(workspaceId);
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: tagKeys.all(workspaceId) }),
      ...(records ? [refresh()] : []),
    ]);
}

export function useCreateTag(workspaceId: string) {
  const after = useAfterChange(workspaceId, false);
  return useMutation<Tag, ApiError, { name: string }>({
    mutationFn: async ({ name }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/tags", {
          params: { path: where(workspaceId) },
          body: { name },
        }),
      ),
    onSettled: () => after(),
  });
}

export function useRenameTag(workspaceId: string) {
  const after = useAfterChange(workspaceId, true);
  return useMutation<Tag, ApiError, { id: string; version: number; name: string }>({
    mutationFn: async ({ id, version, name }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/tags/{tag_id}", {
          params: { path: { tenant_id: workspaceId, tag_id: id }, header: ifMatch(version) },
          body: { name },
        }),
      ),
    onSettled: () => after(),
  });
}

export function useDeleteTag(workspaceId: string) {
  const after = useAfterChange(workspaceId, true);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/tags/{tag_id}", {
            params: { path: { tenant_id: workspaceId, tag_id: id } },
          })
        ).response,
      ),
    onSettled: () => after(),
  });
}
