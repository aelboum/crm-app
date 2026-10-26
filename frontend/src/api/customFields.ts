import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { ifMatch, unwrapWrite, useRefresh, where } from "./records";
import type { components } from "./schema";

/*
 * Custom field definitions (decision P3-D). Every role reads them; Owners
 * and Admins create, change, archive and restore them (`update_workspace`
 * in `/access`). Changing a definition changes what records show, so both
 * kinds of record are re-read afterwards.
 */

export type FieldDefinition = components["schemas"]["DefinitionOut"];
export type FieldEntity = FieldDefinition["entity"];
export type FieldType = FieldDefinition["field_type"];
export type DefinitionCreate = components["schemas"]["DefinitionCreate"];
export type DefinitionUpdate = components["schemas"]["DefinitionUpdate"];

export const FIELD_TYPES: readonly FieldType[] = ["text", "number", "date", "boolean", "select"];

export const fieldKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "custom-fields"] as const,
};

/** Every definition of the workspace, archived ones included. */
export function useFieldDefinitions(workspaceId: string) {
  return useQuery({
    queryKey: fieldKeys.all(workspaceId),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/custom-fields", { params: { path: where(workspaceId) } })),
  });
}

/** The entity's active fields, in their order. */
export function activeFields(definitions: FieldDefinition[] | undefined, entity: FieldEntity): FieldDefinition[] {
  return (definitions ?? []).filter((field) => field.entity === entity && !field.archived);
}

function useAfterChange(workspaceId: string) {
  const client = useQueryClient();
  const refresh = useRefresh(workspaceId);
  return () => Promise.all([client.invalidateQueries({ queryKey: fieldKeys.all(workspaceId) }), refresh()]);
}

const item = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, field_id: id });

export function useCreateField(workspaceId: string) {
  const after = useAfterChange(workspaceId);
  return useMutation<FieldDefinition, ApiError, DefinitionCreate>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/custom-fields", { params: { path: where(workspaceId) }, body }),
      ),
    onSettled: () => after(),
  });
}

export function useUpdateField(workspaceId: string) {
  const after = useAfterChange(workspaceId);
  return useMutation<FieldDefinition, ApiError, { id: string; version: number; changes: DefinitionUpdate }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/custom-fields/{field_id}", {
          params: { path: item(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => after(),
  });
}

export function useArchiveField(workspaceId: string) {
  const after = useAfterChange(workspaceId);
  return useMutation<FieldDefinition, ApiError, { id: string; archived: boolean }>({
    mutationFn: async ({ id, archived }) => {
      const params = { params: { path: item(workspaceId, id) } };
      return archived
        ? unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/custom-fields/{field_id}/archive", params))
        : unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/custom-fields/{field_id}/restore", params));
    },
    onSettled: () => after(),
  });
}
