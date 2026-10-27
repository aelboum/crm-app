import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Tasks (decision P4-C). Every role reads; Owners, Admins and Members
 * create, change, complete, reopen and delete them (`create_task`,
 * `update_task`, `delete_task` in `/access`). Due times travel as ISO
 * timestamps with their offset; "today" is the viewer's own day, so it is
 * computed here.
 */

export type Task = components["schemas"]["TaskOut"];
export type TaskPage = components["schemas"]["TaskPage"];
export type TaskCreate = components["schemas"]["TaskIn"];
export type TaskChanges = components["schemas"]["TaskPatch"];
export type TaskCounts = components["schemas"]["TaskCounts"];
export type Priority = "high" | "medium" | "low";
export const PRIORITIES: readonly Priority[] = ["high", "medium", "low"];

export interface TaskFilters {
  status: "open" | "done" | "all";
  assignees: string[];
  overdue: boolean;
  contactIds: string[];
  companyIds: string[];
  opportunityIds: string[];
  sort: "due_at" | "completed_at" | "created_at" | "updated_at";
  direction: "asc" | "desc";
}

export const NO_TASK_FILTERS: TaskFilters = {
  status: "open",
  assignees: [],
  overdue: false,
  contactIds: [],
  companyIds: [],
  opportunityIds: [],
  sort: "due_at",
  direction: "asc",
};

export const taskKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "tasks"] as const,
  list: (workspaceId: string, filters: TaskFilters) => [...taskKeys.all(workspaceId), "list", filters] as const,
  counts: (workspaceId: string, assignees: string[]) => [...taskKeys.all(workspaceId), "counts", assignees] as const,
};

export function useTaskList(workspaceId: string, filters: TaskFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: taskKeys.list(workspaceId, filters),
    enabled,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: TaskPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<TaskPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/tasks", {
          params: {
            path: where(workspaceId),
            query: {
              status: filters.status,
              sort: filters.sort,
              direction: filters.direction,
              limit: 100,
              ...(filters.assignees.length ? { assignee: filters.assignees } : {}),
              ...(filters.overdue ? { overdue: true } : {}),
              ...(filters.contactIds.length ? { contact_id: filters.contactIds } : {}),
              ...(filters.companyIds.length ? { company_id: filters.companyIds } : {}),
              ...(filters.opportunityIds.length ? { opportunity_id: filters.opportunityIds } : {}),
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
  });
}

export function useTaskCounts(workspaceId: string, assignees: string[]) {
  return useQuery({
    queryKey: taskKeys.counts(workspaceId, assignees),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/tasks/counts", {
          params: { path: where(workspaceId), query: assignees.length ? { assignee: assignees } : {} },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: taskKeys.all(workspaceId) });
}

const one = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, task_id: id });

export function useCreateTask(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Task, ApiError, { body: TaskCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/tasks", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateTask(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Task, ApiError, { id: string; version: number; changes: TaskChanges }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/tasks/{task_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteTask(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (await api.DELETE("/v1/workspaces/{tenant_id}/tasks/{task_id}", { params: { path: one(workspaceId, id) } }))
          .response,
      ),
    onSettled: () => refresh(),
  });
}

/** The quick-add due choices (the design's Today, Tomorrow, Next week), at 17:00 local time. */
export type DuePreset = "none" | "today" | "tomorrow" | "nextWeek";

export function dueFromPreset(preset: DuePreset, now: Date = new Date()): string | null {
  if (preset === "none") return null;
  const due = new Date(now);
  due.setHours(17, 0, 0, 0);
  if (preset === "tomorrow") due.setDate(due.getDate() + 1);
  if (preset === "nextWeek") due.setDate(due.getDate() + 7);
  return due.toISOString();
}

export type DueGroup = "overdue" | "today" | "upcoming" | "none";

/** Where an open task belongs in the design's groups, by the viewer's own day. */
export function dueGroup(task: Task, now: Date = new Date()): DueGroup {
  if (!task.due_at) return "none";
  const due = new Date(task.due_at);
  if (due.getTime() < now.getTime()) return "overdue";
  const endOfToday = new Date(now);
  endOfToday.setHours(24, 0, 0, 0);
  return due.getTime() < endOfToday.getTime() ? "today" : "upcoming";
}
