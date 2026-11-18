import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { where } from "./records";
import type { components } from "./schema";

/*
 * Settings › AI (decision P9-S), over SaaS-OS's tenant AI settings. Owners
 * and Admins only (`read_ai_settings`, `manage_ai_settings`,
 * `read_ai_usage`, `manage_ai_budget`). Every write answers 204; the
 * settings and the budget are read again afterwards.
 */

export type AISettings = components["schemas"]["AISettingsOut"];
export type AIModel = components["schemas"]["ModelOut"];
export type AIFeature = components["schemas"]["FeatureOut"]["feature"];
export type AIPreferences = components["schemas"]["PreferencesIn"];
export type AIModelChoice = components["schemas"]["ModelIn"];
export type AIBudget = components["schemas"]["BudgetOut"];
export type AIBudgetCap = components["schemas"]["BudgetIn"];

export const aiKeys = {
  settings: (workspaceId: string) =>
    ["workspace", workspaceId, "ai", "settings"] as const,
  budget: (workspaceId: string) =>
    ["workspace", workspaceId, "ai", "budget"] as const,
};

export function useAISettings(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.settings(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/ai", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

export function useAIBudget(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.budget(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/ai/budget", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

/** A 204 write; a refusal keeps its closed reason code. */
function noContent(result: { error?: unknown; response: Response }): null {
  if (result.response.ok) return null;
  const detail =
    typeof result.error === "object" &&
    result.error !== null &&
    "detail" in result.error
      ? result.error.detail
      : undefined;
  const code =
    typeof detail === "object" &&
    detail !== null &&
    "code" in detail &&
    typeof detail.code === "string"
      ? detail.code
      : undefined;
  throw new ApiError(result.response.status, code);
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: ["workspace", workspaceId, "ai"] });
}

export function useSetAIEnabled(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, boolean>({
    mutationFn: async (enabled) =>
      noContent(
        await api.PUT("/v1/workspaces/{tenant_id}/ai/enabled", {
          params: { path: where(workspaceId) },
          body: { enabled },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useSetAIFeature(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { feature: AIFeature; enabled: boolean }>({
    mutationFn: async ({ feature, enabled }) =>
      noContent(
        await api.PUT("/v1/workspaces/{tenant_id}/ai/features/{feature}", {
          params: { path: { tenant_id: workspaceId, feature } },
          body: { enabled },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useSetAIPreferences(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, AIPreferences>({
    mutationFn: async (body) =>
      noContent(
        await api.PUT("/v1/workspaces/{tenant_id}/ai/preferences", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useSetAIModel(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, AIModelChoice>({
    mutationFn: async (body) =>
      noContent(
        await api.PUT("/v1/workspaces/{tenant_id}/ai/models", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useSetAIBudgetCap(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, AIBudgetCap>({
    mutationFn: async (body) =>
      noContent(
        await api.PUT("/v1/workspaces/{tenant_id}/ai/budget", {
          params: { path: where(workspaceId) },
          body,
        }),
      ),
    onSettled: () => refresh(),
  });
}
