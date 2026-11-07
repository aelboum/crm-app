import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Webhook endpoints (decision P12-H). Owners and Admins only
 * (`manage_integrations`). The signing secret is shown once, in the
 * response that adds the endpoint.
 */

export type Endpoint = components["schemas"]["EndpointOut"];
export type Delivery = components["schemas"]["DeliveryOut"];
export type AddedEndpoint = components["schemas"]["AddedEndpoint"];

export const webhookKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "webhooks"] as const,
};

export function useWebhooks(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: webhookKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/webhooks", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: webhookKeys.all(workspaceId) });
}

export function useAddWebhook(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<AddedEndpoint, ApiError, { url: string }>({
    mutationFn: async (body) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/webhooks", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useRemoveWebhook(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/webhooks/{endpoint_id}",
            {
              params: { path: { tenant_id: workspaceId, endpoint_id: id } },
            },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
