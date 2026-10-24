import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type ApiError, unwrap } from "./client";
import type { RecordKind } from "./records";
import { recordKeys } from "./records";
import type { components } from "./schema";

/*
 * Notes and history on a contact or company (PHASE3-PLAN.md §21, decision
 * P3-B). Keys sit under the record's own key, so any record change, which
 * re-reads the record's kind (records.ts), also re-reads its history.
 */

export type Note = components["schemas"]["NoteOut"];
export type NotePage = components["schemas"]["NotePage"];
export type Activity = components["schemas"]["ActivityOut"];
export type ActivityPage = components["schemas"]["ActivityPage"];

export const SECTION_PAGE = 5;
/** The API's limit on a note, after line breaks are normalised (crm_app.domains.records). */
export const NOTE_MAX = 10_000;

export const noteKeys = {
  notes: (workspaceId: string, kind: RecordKind, id: string) =>
    [...recordKeys.one(workspaceId, kind, id), "notes"] as const,
  activity: (workspaceId: string, kind: RecordKind, id: string) =>
    [...recordKeys.one(workspaceId, kind, id), "activity"] as const,
};

const record = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, record_id: id });
const note = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, note_id: id });
const page = (cursor: string | undefined) => ({ limit: SECTION_PAGE, ...(cursor ? { cursor } : {}) });

export function useNotes(workspaceId: string, kind: RecordKind, id: string) {
  return useInfiniteQuery({
    queryKey: noteKeys.notes(workspaceId, kind, id),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: NotePage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<NotePage> => {
      const params = { params: { path: record(workspaceId, id), query: page(pageParam) } };
      return unwrap(
        kind === "contacts"
          ? await api.GET("/v1/workspaces/{tenant_id}/contacts/{record_id}/notes", params)
          : await api.GET("/v1/workspaces/{tenant_id}/companies/{record_id}/notes", params),
      );
    },
  });
}

export function useActivity(workspaceId: string, kind: RecordKind, id: string) {
  return useInfiniteQuery({
    queryKey: noteKeys.activity(workspaceId, kind, id),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: ActivityPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<ActivityPage> => {
      const params = { params: { path: record(workspaceId, id), query: page(pageParam) } };
      return unwrap(
        kind === "contacts"
          ? await api.GET("/v1/workspaces/{tenant_id}/contacts/{record_id}/activity", params)
          : await api.GET("/v1/workspaces/{tenant_id}/companies/{record_id}/activity", params),
      );
    },
  });
}

/** Re-reads the record's notes and history after a note change. */
function useRefresh(workspaceId: string, kind: RecordKind, id: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: noteKeys.notes(workspaceId, kind, id) }),
      client.invalidateQueries({ queryKey: noteKeys.activity(workspaceId, kind, id) }),
    ]);
}

/** Adds a note; `key` is the attempt's Idempotency-Key, reused on retry. */
export function useAddNote(workspaceId: string, kind: RecordKind, id: string) {
  const refresh = useRefresh(workspaceId, kind, id);
  return useMutation<Note, ApiError, { body: string; key: string }>({
    mutationFn: async ({ body, key }) => {
      const params = {
        params: { path: record(workspaceId, id), header: { "Idempotency-Key": key } },
        body: { body },
      };
      return unwrap(
        kind === "contacts"
          ? await api.POST("/v1/workspaces/{tenant_id}/contacts/{record_id}/notes", params)
          : await api.POST("/v1/workspaces/{tenant_id}/companies/{record_id}/notes", params),
      );
    },
    onSettled: () => refresh(),
  });
}

export function useEditNote(workspaceId: string, kind: RecordKind, id: string) {
  const refresh = useRefresh(workspaceId, kind, id);
  return useMutation<Note, ApiError, { noteId: string; version: number; body: string }>({
    mutationFn: async ({ noteId, version, body }) =>
      unwrap(
        await api.PATCH("/v1/workspaces/{tenant_id}/notes/{note_id}", {
          params: { path: note(workspaceId, noteId), header: { "If-Match": `"${String(version)}"` } },
          body: { body },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteNote(workspaceId: string, kind: RecordKind, id: string) {
  const refresh = useRefresh(workspaceId, kind, id);
  return useMutation<null, ApiError, { noteId: string }>({
    mutationFn: async ({ noteId }) => {
      const result = await api.DELETE("/v1/workspaces/{tenant_id}/notes/{note_id}", {
        params: { path: note(workspaceId, noteId) },
      });
      // 204 has no body; on refusal `unwrap` throws the status and code.
      if (!result.response.ok) unwrap(result);
      return null;
    },
    onSettled: () => refresh(),
  });
}
