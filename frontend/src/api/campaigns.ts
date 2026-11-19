import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { ExportError, fileNameFrom } from "./exportContacts";
import { ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Campaigns (decision P7-C). Every role reads them (`read_campaigns`);
 * Owners, Admins and Members draft, edit, validate, submit and cancel
 * (`manage_campaigns`); Owners and Admins approve, reject and queue
 * (`approve_campaigns`). Editing returns a campaign to draft and clears its
 * approval. Queuing is refused while campaign sending is unavailable,
 * which the list reports as `sending_available`. Finished campaigns can be
 * archived and unarchived (decision P7-AR, `manage_campaigns`): archived
 * ones are listed only on request (`archived`). Any campaign can be
 * duplicated into a new draft (decision P7-DU, `manage_campaigns`).
 */

export type Campaign = components["schemas"]["CampaignOut"];
export type CampaignStatus = Campaign["status"];
export type CampaignInput = components["schemas"]["CampaignIn"];
export type Step =
  | "validate"
  | "submit"
  | "approve"
  | "cancel"
  | "queue"
  | "archive"
  | "unarchive"
  | "unschedule";
export type CampaignReport = components["schemas"]["CampaignReport"];
export type Outcome = keyof CampaignReport["outcomes"];

export const campaignKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "campaigns"] as const,
};

/*
 * The list's filters (decision P7-CL): archived or current, one status,
 * and part of the name. Pages of 50 in `order` (decision P7-SO: newest
 * first, last updated first, or by name); `fetchNextPage` follows the
 * server's cursor.
 */
export type CampaignOrder = "created_at" | "updated_at" | "name";

export type CampaignFilters = {
  order: CampaignOrder;
  archived: boolean;
  status: CampaignStatus | null;
  search: string;
};

export type CampaignPage = components["schemas"]["CampaignList"];

export function useCampaigns(workspaceId: string, filters: CampaignFilters) {
  const search = filters.search.trim();
  return useInfiniteQuery({
    queryKey: [
      ...campaignKeys.all(workspaceId),
      "list",
      filters.order,
      filters.archived,
      filters.status,
      search,
    ],
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: CampaignPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<CampaignPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/campaigns", {
          params: {
            path: where(workspaceId),
            query: {
              limit: 50,
              ...(filters.order !== "created_at"
                ? { order: filters.order }
                : {}),
              ...(filters.archived ? { archived: true } : {}),
              ...(filters.status ? { status: filters.status } : {}),
              ...(search ? { search } : {}),
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: campaignKeys.all(workspaceId) });
}

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  campaign_id: id,
});

export function useCreateCampaign(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Campaign, ApiError, CampaignInput>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/campaigns", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateCampaign(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Campaign,
    ApiError,
    { id: string; version: number; changes: Partial<CampaignInput> }
  >({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/campaigns/{campaign_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useCampaignStep(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Campaign,
    ApiError,
    { id: string; version: number; step: Step }
  >({
    mutationFn: async ({ id, version, step }) => {
      const params = {
        params: { path: one(workspaceId, id), header: ifMatch(version) },
      };
      switch (step) {
        case "validate":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/validate",
              params,
            ),
          );
        case "submit":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/submit",
              params,
            ),
          );
        case "approve":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/approve",
              params,
            ),
          );
        case "cancel":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/cancel",
              params,
            ),
          );
        case "queue":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/queue",
              params,
            ),
          );
        case "archive":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/archive",
              params,
            ),
          );
        case "unarchive":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/unarchive",
              params,
            ),
          );
        case "unschedule":
          return unwrapWrite(
            await api.POST(
              "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/unschedule",
              params,
            ),
          );
      }
    },
    onSettled: () => refresh(),
  });
}

/*
 * A campaign's results (decision P7-RP): its recipients by email outcome,
 * counted from stored rows, and unsubscribes. Refreshed every 30 seconds
 * while it is still being processed.
 */
export function useCampaignReport(
  workspaceId: string,
  id: string,
  live: boolean,
) {
  return useQuery({
    queryKey: [...campaignKeys.all(workspaceId), id, "report"],
    refetchInterval: live ? 30_000 : false,
    queryFn: async () =>
      unwrap(
        await api.GET(
          "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/report",
          { params: { path: one(workspaceId, id) } },
        ),
      ),
  });
}

/*
 * Queue an approved campaign at a later time (decision P7-SC): Owners and
 * Admins, from 5 minutes to 90 days ahead, under the same conditions as
 * queuing now. Editing, cancelling or Unschedule clears the time.
 */
export function useScheduleCampaign(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Campaign,
    ApiError,
    { id: string; version: number; at: string }
  >({
    mutationFn: async ({ id, version, at }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/schedule",
          {
            params: { path: one(workspaceId, id), header: ifMatch(version) },
            body: { at },
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export type CampaignPreview = components["schemas"]["CampaignPreview"];

/*
 * The campaign as one contact would receive it (decision P7-PV), and
 * whether they are in the audience and may receive it. Nothing is sent.
 */
export function useCampaignPreview(
  workspaceId: string,
  id: string,
  contactId: string | null,
  version: number,
) {
  return useQuery({
    queryKey: [
      ...campaignKeys.all(workspaceId),
      id,
      "preview",
      contactId,
      version,
    ],
    enabled: contactId !== null,
    queryFn: async (): Promise<CampaignPreview> =>
      unwrap(
        await api.GET(
          "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/preview",
          {
            params: {
              path: one(workspaceId, id),
              query: { contact_id: contactId ?? "" },
            },
          },
        ),
      ),
  });
}

/** A new draft with the campaign's subject, body and audience (P7-DU). */
export function useDuplicateCampaign(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Campaign, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/duplicate",
          { params: { path: one(workspaceId, id) }, body: {} },
        ),
      ),
    onSuccess: () => refresh(),
  });
}

/*
 * A campaign's recipients and outcomes as CSV (decision P7-RX): Owners and
 * Admins (`export_records`), counted against a limit per user, so never
 * retried automatically.
 */
export async function exportCampaignResults(
  workspaceId: string,
  id: string,
): Promise<{ blob: Blob; fileName: string }> {
  let result;
  try {
    result = await api.GET(
      "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/results.csv",
      { params: { path: one(workspaceId, id) }, parseAs: "blob" },
    );
  } catch {
    throw new ExportError(0, null);
  }
  const { response } = result;
  const data: unknown = result.data;
  if (!response.ok || !(data instanceof Blob)) {
    throw new ExportError(response.status, null);
  }
  return {
    blob: data,
    fileName: fileNameFrom(
      response.headers.get("Content-Disposition"),
      "campaign-results",
    ),
  };
}

export function useRejectCampaign(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Campaign,
    ApiError,
    { id: string; version: number; note: string }
  >({
    mutationFn: async ({ id, version, note }) =>
      unwrapWrite(
        await api.POST(
          "/v1/workspaces/{tenant_id}/campaigns/{campaign_id}/reject",
          {
            params: { path: one(workspaceId, id), header: ifMatch(version) },
            body: { note },
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}
