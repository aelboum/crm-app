import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { formKeys } from "./forms";
import { expectNoContent, where } from "./records";
import type { components } from "./schema";

/*
 * Consent and suppression (decision P7-B). Owners, Admins and Members read
 * the suppression list (`read_suppressions`); Owners and Admins add and
 * remove addresses (`manage_suppressions`). Members record and withdraw a
 * contact's consent (`update_contact`); withdrawing also suppresses the
 * address. Nothing here sends email: these are the checks a send will pass.
 */

export type Suppression = components["schemas"]["SuppressionOut"];
export type SuppressionPage = components["schemas"]["SuppressionPage"];
export type Reason = Suppression["reason"];
export type EmailStatus = components["schemas"]["EmailStatus"];

export const REASONS: readonly Reason[] = ["manual", "unsubscribed", "bounced", "complained"];
export const ADD_MAX = 1000;

export const suppressionKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "suppressions"] as const,
  list: (workspaceId: string, search: string) => [...suppressionKeys.all(workspaceId), "list", search] as const,
  status: (workspaceId: string, contactId: string) => ["workspace", workspaceId, "email-status", contactId] as const,
};

/** Addresses pasted one per line or separated by commas or semicolons. */
export function splitAddresses(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

export function useSuppressions(workspaceId: string, search: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: suppressionKeys.list(workspaceId, search),
    enabled,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: SuppressionPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<SuppressionPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/suppressions", {
          params: {
            path: where(workspaceId),
            query: { limit: 50, ...(search ? { search } : {}), ...(pageParam ? { cursor: pageParam } : {}) },
          },
        }),
      ),
  });
}

/** Refused addresses, by their position in the list sent. */
export class AddressesRefused extends ApiError {
  readonly positions: number[];

  constructor(positions: number[]) {
    super(422, "invalid_emails");
    this.name = "AddressesRefused";
    this.positions = positions;
  }
}

function positionsOf(error: unknown): number[] | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const detail = error.detail;
  if (typeof detail !== "object" || detail === null || !("positions" in detail)) return undefined;
  const positions = detail.positions;
  return Array.isArray(positions) ? positions.filter((p): p is number => typeof p === "number") : undefined;
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: suppressionKeys.all(workspaceId) });
    await client.invalidateQueries({ queryKey: ["workspace", workspaceId, "email-status"] });
  };
}

export function useAddSuppressions(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    components["schemas"]["Added"],
    ApiError,
    { emails: string[]; reason: Reason; note: string | null }
  >({
    mutationFn: async (body) => {
      const result = await api.POST("/v1/workspaces/{tenant_id}/suppressions", {
        params: { path: where(workspaceId) },
        body,
      });
      if (result.response.ok && result.data !== undefined) return result.data;
      const positions = result.response.status === 422 ? positionsOf(result.error) : undefined;
      if (positions) throw new AddressesRefused(positions);
      return unwrap(result);
    },
    onSettled: () => refresh(),
  });
}

export function useRemoveSuppression(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/suppressions/{suppression_id}", {
            params: { path: { tenant_id: workspaceId, suppression_id: id } },
          })
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

// --- A contact's consent --------------------------------------------------------------

const contactPath = (workspaceId: string, contactId: string) => ({ tenant_id: workspaceId, record_id: contactId });

export function useEmailStatus(workspaceId: string, contactId: string) {
  return useQuery({
    queryKey: suppressionKeys.status(workspaceId, contactId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/contacts/{record_id}/email-status", {
          params: { path: contactPath(workspaceId, contactId) },
        }),
      ),
  });
}

function useConsentChange(workspaceId: string, contactId: string) {
  const client = useQueryClient();
  return async (status: EmailStatus) => {
    client.setQueryData(suppressionKeys.status(workspaceId, contactId), status);
    await client.invalidateQueries({ queryKey: formKeys.consent(workspaceId, contactId) });
    await client.invalidateQueries({ queryKey: suppressionKeys.all(workspaceId) });
  };
}

export function useRecordConsent(workspaceId: string, contactId: string) {
  const changed = useConsentChange(workspaceId, contactId);
  return useMutation<EmailStatus, ApiError, { wording: string }>({
    mutationFn: async (body) =>
      unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/contacts/{record_id}/consent", {
          params: { path: contactPath(workspaceId, contactId) },
          body,
        }),
      ),
    onSuccess: changed,
  });
}

export function useWithdrawConsent(workspaceId: string, contactId: string) {
  const changed = useConsentChange(workspaceId, contactId);
  return useMutation<EmailStatus, ApiError, { note: string | null }>({
    mutationFn: async (body) =>
      unwrap(
        await api.POST("/v1/workspaces/{tenant_id}/contacts/{record_id}/consent/withdraw", {
          params: { path: contactPath(workspaceId, contactId) },
          body,
        }),
      ),
    onSuccess: changed,
  });
}
