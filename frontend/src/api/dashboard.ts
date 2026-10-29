import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { recordKeys, where } from "./records";
import type { components } from "./schema";
import { taskKeys } from "./tasks";

/*
 * The Home page's own reads (decision P4-D). Every other card reuses the
 * hook of the page it links to, so the numbers agree with that page. These
 * keys sit under the same prefixes as those pages' keys, so a change made
 * there (or a task completed here) refreshes them too.
 */

export type RecentEntry = components["schemas"]["RecentActivityOut"];

export const FEED_SIZE = 10;
export const TODAY_TASKS = 8;

/** Contacts not archived, as the Contacts list counts them. */
export function useContactTotal(workspaceId: string) {
  return useQuery({
    queryKey: [...recordKeys.all(workspaceId, "contacts"), "total"] as const,
    queryFn: async () => {
      const page = unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/contacts", {
          params: {
            path: where(workspaceId),
            query: { archived: "false", limit: 1 },
          },
        }),
      );
      return { total: page.total, capped: page.total_capped };
    },
  });
}

/** Open tasks of every assignee due before `dayEnd`, earliest first. */
export function useTasksDueBy(workspaceId: string, dayEnd: Date) {
  const to = dayEnd.toISOString();
  return useQuery({
    queryKey: [...taskKeys.all(workspaceId), "due-by", to] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/tasks", {
          params: {
            path: where(workspaceId),
            query: {
              status: "open",
              due_to: to,
              sort: "due_at",
              direction: "asc",
              limit: TODAY_TASKS,
            },
          },
        }),
      ),
  });
}

/** The newest history entries across contacts and companies. */
export function useRecentActivity(workspaceId: string) {
  return useQuery({
    queryKey: ["workspace", workspaceId, "activity-feed"] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/activity", {
          params: { path: where(workspaceId), query: { limit: FEED_SIZE } },
        }),
      ),
  });
}
