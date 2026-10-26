import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import type { components } from "./schema";

/*
 * Contacts and companies (PHASE3-PLAN.md §19). Every key starts with the
 * workspace key, so switching workspaces drops them (router.tsx).
 */

export type Contact = components["schemas"]["ContactOut"];
export type ContactCreate = components["schemas"]["ContactCreate"];
export type ContactUpdate = components["schemas"]["ContactUpdate"];
export type Company = components["schemas"]["CompanyOut"];
export type CompanyCreate = components["schemas"]["CompanyCreate"];
export type CompanyUpdate = components["schemas"]["CompanyUpdate"];
export type ContactPage = components["schemas"]["ContactPage"];
export type CompanyPage = components["schemas"]["CompanyPage"];

export type RecordKind = "contacts" | "companies";
export type Stage = "lead" | "prospect" | "customer" | "inactive";
export type Sort = "name" | "created_at" | "updated_at";
export type Direction = "asc" | "desc";
export type Archived = "false" | "true" | "all";

export const STAGES: readonly Stage[] = ["lead", "prospect", "customer", "inactive"];
/** Sources a person may choose (decision P3-A 2). */
export const USER_SOURCES = ["manual", "referral", "other"] as const;
export const LIST_PAGE = 50;

export interface ListFilters {
  q: string;
  sort: Sort;
  direction: Direction;
  archived: Archived;
  owners: string[];
  stages: Stage[];
  companyIds: string[];
  /** Any of these tags (decision P3-C 7). */
  tagIds: string[];
}

export const NO_FILTERS: ListFilters = {
  q: "",
  sort: "name",
  direction: "asc",
  archived: "false",
  owners: [],
  stages: [],
  companyIds: [],
  tagIds: [],
};

export const recordKeys = {
  all: (workspaceId: string, kind: RecordKind) => ["workspace", workspaceId, kind] as const,
  list: (workspaceId: string, kind: RecordKind, filters: ListFilters) =>
    ["workspace", workspaceId, kind, "list", filters] as const,
  one: (workspaceId: string, kind: RecordKind, id: string) =>
    ["workspace", workspaceId, kind, "one", id] as const,
};

/** The API's validation refusal (422): the names of the refused fields. */
export class FieldErrors extends ApiError {
  readonly fields: string[];

  constructor(fields: string[]) {
    super(422);
    this.name = "FieldErrors";
    this.fields = fields;
  }
}

/** A refusal naming an existing record (409 duplicate_email or duplicate_domain). */
export class DuplicateError extends ApiError {
  readonly existingId: string | undefined;

  constructor(code: string, existingId: string | undefined) {
    super(409, code);
    this.name = "DuplicateError";
    this.existingId = existingId;
  }
}

/** A custom field value the server refused (422), naming the field's key (decision P3-D). */
export class CustomFieldError extends ApiError {
  readonly key: string | undefined;

  constructor(code: string, key: string | undefined) {
    super(422, code);
    this.name = "CustomFieldError";
    this.key = key;
  }
}

function detailOf(error: unknown): unknown {
  return typeof error === "object" && error !== null && "detail" in error ? error.detail : undefined;
}

function fieldNames(detail: unknown[]): string[] {
  return detail.flatMap((entry) => {
    if (typeof entry !== "object" || entry === null || !("loc" in entry)) return [];
    const loc: unknown = entry.loc;
    if (!Array.isArray(loc)) return [];
    const last: unknown = loc[loc.length - 1];
    return typeof last === "string" ? [last] : [];
  });
}

/** Like `unwrap`, keeping the details record writes return on refusal. */
export function unwrapWrite<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  const detail = detailOf(result.error);
  const status = result.response.status;
  if (status === 422 && Array.isArray(detail)) throw new FieldErrors(fieldNames(detail));
  if (status === 422 && typeof detail === "object" && detail !== null && "code" in detail) {
    const code = typeof detail.code === "string" ? detail.code : "invalid";
    if (code.includes("custom_field")) {
      throw new CustomFieldError(code, "key" in detail && typeof detail.key === "string" ? detail.key : undefined);
    }
  }
  if (status === 409 && typeof detail === "object" && detail !== null && "code" in detail) {
    const code = typeof detail.code === "string" ? detail.code : "conflict";
    const existing =
      "existing_id" in detail && typeof detail.existing_id === "string" ? detail.existing_id : undefined;
    if (code.startsWith("duplicate_")) throw new DuplicateError(code, existing);
    throw new ApiError(409, code);
  }
  return unwrap(result);
}

/** A write that answers 204 without a body. */
export function expectNoContent(response: Response): null {
  if (!response.ok) throw new ApiError(response.status);
  return null;
}

export const where = (workspaceId: string) => ({ tenant_id: workspaceId });
const item = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, record_id: id });
export const ifMatch = (version: number) => ({ "If-Match": `"${String(version)}"` });

/** Query parameters, leaving out the ones not in use. */
function common(filters: ListFilters, cursor: string | undefined) {
  const q = filters.q.trim();
  return {
    sort: filters.sort,
    direction: filters.direction,
    archived: filters.archived,
    limit: LIST_PAGE,
    ...(q ? { q } : {}),
    ...(filters.owners.length ? { owner: filters.owners } : {}),
    ...(filters.tagIds.length ? { tag_id: filters.tagIds } : {}),
    ...(cursor ? { cursor } : {}),
  };
}

export function useContactList(workspaceId: string, filters: ListFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: recordKeys.list(workspaceId, "contacts", filters),
    enabled,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: ContactPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<ContactPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/contacts", {
          params: {
            path: where(workspaceId),
            query: {
              ...common(filters, pageParam),
              ...(filters.stages.length ? { lifecycle_stage: [...filters.stages] } : {}),
              ...(filters.companyIds.length ? { company_id: filters.companyIds } : {}),
            },
          },
        }),
      ),
  });
}

export function useCompanyList(workspaceId: string, filters: ListFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: recordKeys.list(workspaceId, "companies", filters),
    enabled,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: CompanyPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<CompanyPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/companies", {
          params: { path: where(workspaceId), query: common(filters, pageParam) },
        }),
      ),
  });
}

export function useContact(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: recordKeys.one(workspaceId, "contacts", id ?? ""),
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/contacts/{record_id}", {
          params: { path: item(workspaceId, id ?? "") },
        }),
      ),
  });
}

export function useCompany(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: recordKeys.one(workspaceId, "companies", id ?? ""),
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/companies/{record_id}", {
          params: { path: item(workspaceId, id ?? "") },
        }),
      ),
  });
}

/** Re-reads both kinds after any change: a company change shows on its contacts. */
export function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: recordKeys.all(workspaceId, "contacts") }),
      client.invalidateQueries({ queryKey: recordKeys.all(workspaceId, "companies") }),
    ]);
}

/** A key per create attempt; retrying the same attempt reuses it (crm_app.records.create). */
export function newIdempotencyKey(): string {
  return globalThis.crypto.randomUUID().replaceAll("-", "");
}

export function useCreateContact(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Contact, ApiError, { body: ContactCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/contacts", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useCreateCompany(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Company, ApiError, { body: CompanyCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/companies", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateContact(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Contact, ApiError, { id: string; version: number; changes: ContactUpdate }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/contacts/{record_id}", {
          params: { path: item(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useUpdateCompany(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Company, ApiError, { id: string; version: number; changes: CompanyUpdate }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/companies/{record_id}", {
          params: { path: item(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export type Lifecycle = "archive" | "restore" | "delete";

async function contactLifecycle(workspaceId: string, id: string, action: Lifecycle) {
  const params = { params: { path: item(workspaceId, id) } };
  switch (action) {
    case "archive":
      return unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/contacts/{record_id}/archive", params));
    case "restore":
      return unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/contacts/{record_id}/restore", params));
    case "delete":
      return expectNoContent(
        (await api.DELETE("/v1/workspaces/{tenant_id}/contacts/{record_id}", params)).response,
      );
  }
}

async function companyLifecycle(workspaceId: string, id: string, action: Lifecycle) {
  const params = { params: { path: item(workspaceId, id) } };
  switch (action) {
    case "archive":
      return unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/companies/{record_id}/archive", params));
    case "restore":
      return unwrapWrite(await api.POST("/v1/workspaces/{tenant_id}/companies/{record_id}/restore", params));
    case "delete":
      return expectNoContent(
        (await api.DELETE("/v1/workspaces/{tenant_id}/companies/{record_id}", params)).response,
      );
  }
}

/** Archive, restore or permanently delete one record. */
export function useLifecycle(workspaceId: string, kind: RecordKind) {
  const refresh = useRefresh(workspaceId);
  return useMutation<unknown, ApiError, { id: string; action: Lifecycle }>({
    mutationFn: ({ id, action }) =>
      kind === "contacts"
        ? contactLifecycle(workspaceId, id, action)
        : companyLifecycle(workspaceId, id, action),
    onSettled: () => refresh(),
  });
}

/** Replace a record's tags (decision P3-C 5): a record update with its version. */
export function useSetTags(workspaceId: string, kind: RecordKind) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Contact | Company, ApiError, { id: string; version: number; tagIds: string[] }>({
    mutationFn: async ({ id, version, tagIds }) => {
      const params = { params: { path: item(workspaceId, id), header: ifMatch(version) }, body: { tag_ids: tagIds } };
      return kind === "contacts"
        ? unwrapWrite(await api.PUT("/v1/workspaces/{tenant_id}/contacts/{record_id}/tags", params))
        : unwrapWrite(await api.PUT("/v1/workspaces/{tenant_id}/companies/{record_id}/tags", params));
    },
    onSettled: () => refresh(),
  });
}
