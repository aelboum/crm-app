import { useMutation } from "@tanstack/react-query";

import { api, type ApiError, unwrap } from "./client";
import { where } from "./records";
import type { components } from "./schema";

/*
 * The contact brief (decision P9-B): one short, suggestions-only summary of
 * a contact, written on request for the member who asked and never stored.
 * Only members with `use_ai_brief` ask. While AI is off for the workspace
 * (the default) the answer is the state `unavailable`.
 */

export type Brief = components["schemas"]["BriefOut"];

export function useContactBrief(workspaceId: string, contactId: string) {
  return useMutation<Brief, ApiError>({
    mutationFn: async () =>
      unwrap(
        await api.POST(
          "/v1/workspaces/{tenant_id}/contacts/{contact_id}/brief",
          { params: { path: { ...where(workspaceId), contact_id: contactId } } },
        ),
      ),
  });
}
