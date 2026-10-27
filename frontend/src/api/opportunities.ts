import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { pipelineKeys } from "./pipelines";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Deals (decision P4-B). Every role reads; Owners, Admins and Members create
 * and change deals, stages and outcomes; Owners and Admins delete
 * (`create_opportunity`, `update_opportunity`, `delete_opportunity` in
 * `/access`). Amounts are decimal strings end to end, never numbers. The
 * board and the table read the same list with the same filters, and the
 * board's column counts and totals come from the summary for those filters.
 */

export type Deal = components["schemas"]["DealOut"];
export type DealPage = components["schemas"]["DealPage"];
export type DealSummary = components["schemas"]["DealSummary"];
export type DealEvent = components["schemas"]["DealEvent"];
export type DealCreate = components["schemas"]["DealIn"];
export type DealChanges = components["schemas"]["DealPatch"];
export type Outcome = "open" | "won" | "lost";
export type DealSort = "updated_at" | "created_at" | "title" | "amount" | "expected_close_date";

export const DEAL_PAGE = 100;
export const IDLE_DAYS = 7;

export interface DealFilters {
  q: string;
  outcomes: Outcome[];
  stageIds: string[];
  owners: string[];
  idle: boolean;
  sort: DealSort;
  direction: "asc" | "desc";
}

export const dealKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "opportunities"] as const,
  list: (workspaceId: string, filters: DealFilters) =>
    [...dealKeys.all(workspaceId), "list", filters] as const,
  summary: (workspaceId: string, filters: DealFilters) =>
    [...dealKeys.all(workspaceId), "summary", filters] as const,
  one: (workspaceId: string, id: string) => [...dealKeys.all(workspaceId), "one", id] as const,
  history: (workspaceId: string, id: string) => [...dealKeys.all(workspaceId), "history", id] as const,
};

/** The filters as query parameters, leaving out the ones not in use. */
function filterQuery(filters: DealFilters) {
  const q = filters.q.trim();
  return {
    ...(q ? { q } : {}),
    ...(filters.outcomes.length ? { outcome: filters.outcomes } : {}),
    ...(filters.stageIds.length ? { stage_id: filters.stageIds } : {}),
    ...(filters.owners.length ? { owner: filters.owners } : {}),
    ...(filters.idle ? { idle: true } : {}),
  };
}

export function useDealList(workspaceId: string, filters: DealFilters) {
  return useInfiniteQuery({
    queryKey: dealKeys.list(workspaceId, filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: DealPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<DealPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/opportunities", {
          params: {
            path: where(workspaceId),
            query: {
              ...filterQuery(filters),
              sort: filters.sort,
              direction: filters.direction,
              limit: DEAL_PAGE,
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
  });
}

export function useDealSummary(workspaceId: string, filters: DealFilters) {
  return useQuery({
    queryKey: dealKeys.summary(workspaceId, filters),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/opportunities/summary", {
          params: { path: where(workspaceId), query: filterQuery(filters) },
        }),
      ),
  });
}

const one = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, deal_id: id });

export function useDeal(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: dealKeys.one(workspaceId, id ?? ""),
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/opportunities/{deal_id}", {
          params: { path: one(workspaceId, id ?? "") },
        }),
      ),
  });
}

export function useDealHistory(workspaceId: string, id: string) {
  return useInfiniteQuery({
    queryKey: dealKeys.history(workspaceId, id),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: components["schemas"]["DealHistory"]) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/opportunities/{deal_id}/history", {
          params: {
            path: one(workspaceId, id),
            query: { limit: 20, ...(pageParam ? { cursor: pageParam } : {}) },
          },
        }),
      ),
  });
}

/** Re-reads every deal view, and the pipeline, whose stages a deal names. */
function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: dealKeys.all(workspaceId) }),
      client.invalidateQueries({ queryKey: pipelineKeys.all(workspaceId) }),
    ]);
}

export function useCreateDeal(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Deal, ApiError, { body: DealCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/opportunities", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateDeal(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Deal, ApiError, { id: string; version: number; changes: DealChanges }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/opportunities/{deal_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useSetOutcome(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Deal, ApiError, { id: string; version: number; outcome: Outcome; reason?: string }>({
    mutationFn: async ({ id, version, outcome, reason }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/opportunities/{deal_id}/outcome", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: { outcome, ...(reason === undefined ? {} : { lost_reason: reason }) },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteDeal(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/opportunities/{deal_id}", {
            params: { path: one(workspaceId, id) },
          })
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

/** Digits after the point for a currency, as the server checks them (P4-B 2). */
const ZERO_DIGITS = [
  "BIF",
  "CLP",
  "DJF",
  "GNF",
  "ISK",
  "JPY",
  "KMF",
  "KRW",
  "PYG",
  "RWF",
  "UGX",
  "VND",
  "VUV",
  "XAF",
  "XOF",
  "XPF",
];
const THREE_DIGITS = ["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"];

export function minorDigits(currency: string): number {
  if (ZERO_DIGITS.includes(currency)) return 0;
  return THREE_DIGITS.includes(currency) ? 3 : 2;
}

/**
 * The amount as the API takes it, or null when the text is not a valid
 * amount in `currency`. Spaces are removed; nothing is ever rounded.
 */
export function amountText(raw: string, currency: string): string | null {
  const text = raw.replaceAll(" ", "");
  const match = /^(0|[1-9][0-9]{0,11})(?:\.([0-9]+))?$/.exec(text);
  if (!match) return null;
  return (match[2] ?? "").length <= minorDigits(currency) ? text : null;
}
