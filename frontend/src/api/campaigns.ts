import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Campaigns (decision P7-C). Every role reads them (`read_campaigns`);
 * Owners, Admins and Members draft, edit, validate, submit and cancel
 * (`manage_campaigns`); Owners and Admins approve, reject and queue
 * (`approve_campaigns`). Editing returns a campaign to draft and clears its
 * approval. Queuing is refused while campaign sending is unavailable,
 * which the list reports as `sending_available`.
 */

export type Campaign = components["schemas"]["CampaignOut"];
export type CampaignStatus = Campaign["status"];
export type CampaignInput = components["schemas"]["CampaignIn"];
export type Step = "validate" | "submit" | "approve" | "cancel" | "queue";

export const campaignKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "campaigns"] as const,
};

export function useCampaigns(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: campaignKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/campaigns", {
          params: { path: where(workspaceId) },
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
      }
    },
    onSettled: () => refresh(),
  });
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
