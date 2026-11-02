import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Automations (decision P8-A). Every role reads them and their runs
 * (`read_automations`); Owners and Admins create, edit, activate, pause and
 * delete them (`manage_automations`). A definition is plain data checked by
 * the server; this module only types it.
 */

export type Automation = components["schemas"]["AutomationOut"];
export type AutomationRun = components["schemas"]["RunOut"];

export type Source = "manual" | "form" | "booking" | "referral" | "other";
export const TRIGGER_SOURCES: Source[] = [
  "manual",
  "form",
  "booking",
  "referral",
  "other",
];
export const MAX_ACTIONS = 10;

export type Action =
  | { type: "add_tag"; tag_id: string }
  | { type: "remove_tag"; tag_id: string }
  | { type: "assign_owner"; user_id: string }
  | { type: "set_lifecycle_stage"; stage: string }
  | {
      type: "create_task";
      title: string;
      priority: "high" | "medium" | "low";
      due_minutes: number | null;
      assignee: string;
    }
  | { type: "wait"; minutes: number };

export type Condition =
  | {
      field: "source" | "lifecycle_stage";
      op: "in" | "not_in";
      values: string[];
    }
  | { field: "email"; op: "present" | "absent" }
  | { field: "tag"; op: "has" | "has_not"; values: string[] };

/*
 * Triggers (decision P8-B adds all but the first). The tag and stage
 * triggers need their record; the form and booking-page ones run for any
 * when theirs is null. Each automation runs at most once per contact.
 */
export type Trigger =
  | { type: "contact_created"; sources: Source[] }
  | { type: "tag_added"; tag_id: string }
  | { type: "form_submitted"; form_id: string | null }
  | { type: "appointment_booked"; booking_page_id: string | null }
  | { type: "deal_stage_changed"; stage_id: string };
export type TriggerType = Trigger["type"];
export const TRIGGER_TYPES: TriggerType[] = [
  "contact_created",
  "tag_added",
  "form_submitted",
  "appointment_booked",
  "deal_stage_changed",
];

export interface Definition {
  trigger: Trigger;
  condition: Condition | null;
  yes: Action[];
  no: Action[];
}

export const EMPTY_DEFINITION: Definition = {
  trigger: { type: "contact_created", sources: [] },
  condition: null,
  yes: [],
  no: [],
};

export const automationKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "automations"] as const,
  runs: (workspaceId: string, id: string) =>
    [...automationKeys.all(workspaceId), "runs", id] as const,
};

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  automation_id: id,
});

export function useAutomations(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: automationKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/automations", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

export function useAutomationRuns(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: automationKeys.runs(workspaceId, id ?? ""),
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET(
          "/v1/workspaces/{tenant_id}/automations/{automation_id}/runs",
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
    client.invalidateQueries({ queryKey: automationKeys.all(workspaceId) });
}

function asBody(definition: Definition): Record<string, unknown> {
  return definition as unknown as Record<string, unknown>;
}

export function useCreateAutomation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Automation,
    ApiError,
    { name: string; definition: Definition }
  >({
    mutationFn: async ({ name, definition }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/automations", {
          params: { path: where(workspaceId) },
          body: { name, definition: asBody(definition) },
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateAutomation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Automation,
    ApiError,
    { id: string; version: number; name: string; definition?: Definition }
  >({
    mutationFn: async ({ id, version, name, definition }) =>
      unwrapWrite(
        await api.PATCH(
          "/v1/workspaces/{tenant_id}/automations/{automation_id}",
          {
            params: { path: one(workspaceId, id), header: ifMatch(version) },
            body:
              definition === undefined
                ? { name }
                : { name, definition: asBody(definition) },
          },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useSwitchAutomation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Automation,
    ApiError,
    { id: string; version: number; to: "activate" | "pause" }
  >({
    mutationFn: async ({ id, version, to }) => {
      const params = { path: one(workspaceId, id), header: ifMatch(version) };
      return unwrapWrite(
        to === "activate"
          ? await api.POST(
              "/v1/workspaces/{tenant_id}/automations/{automation_id}/activate",
              { params },
            )
          : await api.POST(
              "/v1/workspaces/{tenant_id}/automations/{automation_id}/pause",
              { params },
            ),
      );
    },
    onSettled: () => refresh(),
  });
}

export function useDeleteAutomation(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/automations/{automation_id}",
            {
              params: { path: one(workspaceId, id) },
            },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}
