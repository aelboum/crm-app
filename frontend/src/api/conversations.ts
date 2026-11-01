import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Conversations (decision P6-C). Every role reads them
 * (`read_conversations`); Owners, Admins and Members reply, log messages,
 * add notes, assign and close (`reply_conversations`). An email reply is
 * queued, not sent: its `delivery` is the email's status, and "queued"
 * means it has not left.
 */

export type ConversationSummary = components["schemas"]["ConversationSummary"];
export type Conversation = components["schemas"]["ConversationOut"];
export type ConversationMessage = components["schemas"]["MessageOut"];
export type MessageKind = "inbound" | "outbound" | "note";
export type Channel = "email" | "other";
export type Assigned = "all" | "mine" | "unassigned";

export interface InboxFilter {
  status: "open" | "closed";
  assigned: Assigned;
}

export const conversationKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "conversations"] as const,
  lists: (workspaceId: string) =>
    [...conversationKeys.all(workspaceId), "list"] as const,
  list: (workspaceId: string, filter: InboxFilter) =>
    [...conversationKeys.lists(workspaceId), filter] as const,
  one: (workspaceId: string, id: string) =>
    [...conversationKeys.all(workspaceId), "one", id] as const,
};

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  conversation_id: id,
});

export function useConversations(workspaceId: string, filter: InboxFilter) {
  return useQuery({
    queryKey: conversationKeys.list(workspaceId, filter),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/conversations", {
          params: { path: where(workspaceId), query: filter },
        }),
      ),
  });
}

export function useConversation(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: conversationKeys.one(workspaceId, id ?? ""),
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET(
          "/v1/workspaces/{tenant_id}/conversations/{conversation_id}",
          {
            params: { path: one(workspaceId, id ?? "") },
          },
        ),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: conversationKeys.all(workspaceId) });
}

export interface NewConversation {
  contact_id: string;
  channel: Channel;
  subject: string;
  kind: MessageKind;
  body: string;
}

export function useCreateConversation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Conversation,
    ApiError,
    { body: NewConversation; key: string }
  >({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/conversations", {
          params: {
            path: where(workspaceId),
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useAddMessage(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Conversation,
    ApiError,
    { id: string; kind: MessageKind; body: string; key: string }
  >({
    mutationFn: async ({ id, kind, body, key }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/conversations/{conversation_id}/messages",
          {
            params: {
              path: one(workspaceId, id),
              header: { "Idempotency-Key": key },
            },
            body: { kind, body },
          },
        ),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateConversation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Conversation,
    ApiError,
    {
      id: string;
      version: number;
      changes: { status?: "open" | "closed"; assignee_user_id?: string | null };
    }
  >({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH(
          "/v1/workspaces/{tenant_id}/conversations/{conversation_id}",
          {
            params: { path: one(workspaceId, id), header: ifMatch(version) },
            body: changes,
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useMarkRead(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.POST(
            "/v1/workspaces/{tenant_id}/conversations/{conversation_id}/read",
            {
              params: { path: one(workspaceId, id) },
            },
          )
        ).response,
      ),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: conversationKeys.lists(workspaceId),
      }),
  });
}
