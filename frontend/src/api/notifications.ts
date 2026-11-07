import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { expectNoContent, where } from "./records";
import type { components } from "./schema";

/*
 * The signed-in member's own notifications (decision N-1). Every role has
 * them; the server always answers for the caller, never another member.
 * The list refreshes every minute while the app is open and when the
 * window regains focus, so the bell's dot stays current without a push
 * channel.
 */

export type Notification = components["schemas"]["NotificationOut"];
export type NotificationPage = components["schemas"]["NotificationPage"];

export const POLL_MS = 60_000;

export const notificationKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "notifications"] as const,
};

export function useNotifications(workspaceId: string) {
  return useInfiniteQuery({
    queryKey: notificationKeys.all(workspaceId),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: NotificationPage) => last.next_cursor ?? undefined,
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: true,
    queryFn: async ({ pageParam }): Promise<NotificationPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/me/notifications", {
          params: {
            path: where(workspaceId),
            query: pageParam ? { cursor: pageParam } : {},
          },
        }),
      ),
  });
}

export function useMarkNotificationRead(workspaceId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (notificationId: string) => {
      const result = await api.POST(
        "/v1/workspaces/{tenant_id}/me/notifications/{notification_id}/read",
        { params: { path: { tenant_id: workspaceId, notification_id: notificationId } } },
      );
      return expectNoContent(result.response);
    },
    onSettled: () => client.invalidateQueries({ queryKey: notificationKeys.all(workspaceId) }),
  });
}

export function useMarkAllNotificationsRead(workspaceId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/me/notifications/read-all", {
          params: { path: where(workspaceId) },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: notificationKeys.all(workspaceId) }),
  });
}

/** Where a notification's record opens. */
const SECTIONS = {
  task: "tasks",
  conversation: "inbox",
  appointment: "calendar",
  contact: "contacts",
} as const;

export function notificationTarget(item: Notification): {
  section: (typeof SECTIONS)[keyof typeof SECTIONS];
  record: string;
} {
  return { section: SECTIONS[item.subject_type], record: item.subject_id };
}
