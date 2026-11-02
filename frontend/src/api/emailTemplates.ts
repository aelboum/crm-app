import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Email templates (decision P7-T): a name, subject and plain-text body with
 * the campaign placeholders. Every role reads them (`read_campaigns`);
 * members who may manage campaigns change them; the reply composer asks
 * for one filled in for the conversation's contact. A template never sends
 * anything.
 */

export type EmailTemplate = components["schemas"]["TemplateOut"];
export type TemplateInput = components["schemas"]["TemplateIn"];
export type Rendered = components["schemas"]["Rendered"];

export const templateKeys = {
  all: (workspaceId: string) =>
    ["workspace", workspaceId, "email-templates"] as const,
};

const one = (workspaceId: string, id: string) => ({
  tenant_id: workspaceId,
  template_id: id,
});

export function useEmailTemplates(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: templateKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/email-templates", {
          params: { path: where(workspaceId) },
        }),
      ),
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    client.invalidateQueries({ queryKey: templateKeys.all(workspaceId) });
}

export function useSaveTemplate(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    EmailTemplate,
    ApiError,
    { template: EmailTemplate | null; body: TemplateInput }
  >({
    mutationFn: async ({ template, body }) =>
      template
        ? unwrapWrite(
            await api.PATCH(
              "/v1/workspaces/{tenant_id}/email-templates/{template_id}",
              {
                params: {
                  path: one(workspaceId, template.id),
                  header: ifMatch(template.version),
                },
                body,
              },
            ),
          )
        : unwrapWrite(
            await api.POST("/v1/workspaces/{tenant_id}/email-templates", {
              params: { path: where(workspaceId) },
              body,
            }),
          ),
    onSettled: () => refresh(),
  });
}

export function useDeleteTemplate(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE(
            "/v1/workspaces/{tenant_id}/email-templates/{template_id}",
            {
              params: { path: one(workspaceId, id) },
            },
          )
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

/** The template filled in for one of the workspace's contacts. */
export async function renderTemplate(
  workspaceId: string,
  id: string,
  contactId: string,
): Promise<Rendered> {
  return unwrapWrite(
    await api.POST(
      "/v1/workspaces/{tenant_id}/email-templates/{template_id}/render",
      {
        params: { path: one(workspaceId, id) },
        body: { contact_id: contactId },
      },
    ),
  );
}
