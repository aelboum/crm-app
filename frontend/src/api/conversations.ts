import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

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
export type Review = components["schemas"]["ReviewOut"];
export type MessageKind = "inbound" | "outbound" | "note";
export type Channel = "email" | "other";
export type Assigned = "all" | "mine" | "unassigned";

export type ConversationPage = components["schemas"]["ConversationList"];
export type InboxStatus = "open" | "closed" | "all";
/** The API's limit on a search (decision P6-C1). */
export const SEARCH_MAX = 100;
const PAGE = 50;

export interface InboxFilter {
  status: InboxStatus;
  assigned: Assigned;
  /** Searched in subjects, message text and contact names; "" lists all. */
  q: string;
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
  reviews: (workspaceId: string) =>
    [...conversationKeys.all(workspaceId), "reviews"] as const,
};

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  conversation_id: id,
});

/** How many of a contact's conversations its drawer shows. */
export const CONTACT_CONVERSATIONS = 5;

/** A contact's most recent conversations, open or closed (its drawer). */
export function useContactConversations(workspaceId: string, contactId: string) {
  return useQuery({
    queryKey: [...conversationKeys.lists(workspaceId), "contact", contactId] as const,
    queryFn: async (): Promise<ConversationPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/conversations", {
          params: {
            path: where(workspaceId),
            query: { status: "all", contact_id: contactId, limit: CONTACT_CONVERSATIONS },
          },
        }),
      ),
  });
}

export function useConversations(workspaceId: string, filter: InboxFilter) {
  return useInfiniteQuery({
    queryKey: conversationKeys.list(workspaceId, filter),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: ConversationPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<ConversationPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/conversations", {
          params: {
            path: where(workspaceId),
            query: {
              status: filter.status,
              assigned: filter.assigned,
              limit: PAGE,
              ...(filter.q ? { q: filter.q } : {}),
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
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

/*
 * Received emails held for review (decision P6-I): mail that reached a
 * thread but did not come from its contact, failed DMARC or had no text.
 * Only members who may reply see and decide them.
 */
export function useReviews(workspaceId: string, enabled: boolean) {
  return useQuery({
    queryKey: conversationKeys.reviews(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/conversation-reviews", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

export function useDecideReview(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Review,
    ApiError,
    { id: string; version: number; accept: boolean }
  >({
    mutationFn: async ({ id, version, accept }) => {
      const params = {
        params: {
          path: { tenant_id: workspaceId, review_id: id },
          header: ifMatch(version),
        },
      };
      return unwrapWrite(
        accept
          ? await api.POST(
              "/v1/workspaces/{tenant_id}/conversation-reviews/{review_id}/accept",
              params,
            )
          : await api.POST(
              "/v1/workspaces/{tenant_id}/conversation-reviews/{review_id}/discard",
              params,
            ),
      );
    },
    onSettled: () => refresh(),
  });
}
