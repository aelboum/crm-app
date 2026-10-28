import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Forms and lead capture (decision P7-A). Every role reads forms, their
 * submissions and a contact's consent (`read_forms`); Owners and Admins
 * create, edit, publish and delete them (`manage_forms`). The hosted page
 * (`/app/f/<workspace>/<key>`) talks to the public routes without a
 * session; its refusals name field keys and rules, never answers.
 */

export type Form = components["schemas"]["FormOut"];
export type FormField = components["schemas"]["FieldIn"];
export type FormCreate = components["schemas"]["FormIn"];
export type FormChanges = components["schemas"]["FormPatch"];
export type Submission = components["schemas"]["SubmissionOut"];
export type SubmissionPage = components["schemas"]["SubmissionPage"];
export type Consent = components["schemas"]["ConsentOut"];
export type PublicForm = components["schemas"]["PublicForm"];
export type FieldType = FormField["type"];
export type Target = NonNullable<FormField["target"]>;

export const FIELD_TYPES: readonly FieldType[] = ["text", "email", "phone", "textarea", "select", "date", "checkbox"];
export const MAX_FIELDS = 20;

/** The contact fields each field type may fill (P7-A 3). */
export const TARGETS: Record<FieldType, readonly Target[]> = {
  text: ["first_name", "last_name", "job_title", "city"],
  email: ["email"],
  phone: ["phone"],
  textarea: [],
  select: [],
  date: [],
  checkbox: [],
};

export const formKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "forms"] as const,
  one: (workspaceId: string, id: string) => [...formKeys.all(workspaceId), "one", id] as const,
  submissions: (workspaceId: string, id: string) => [...formKeys.all(workspaceId), "submissions", id] as const,
  consent: (workspaceId: string, contactId: string) => ["workspace", workspaceId, "consent", contactId] as const,
};

/** The hosted page's address for a form. */
export function publicPath(workspaceId: string, key: string): string {
  return `/app/f/${workspaceId}/${key}`;
}

/** A new field key: lower case, unique within the form. */
export function newFieldKey(type: FieldType, taken: readonly string[]): string {
  for (let n = 1; ; n += 1) {
    const key = n === 1 ? type : `${type}_${String(n)}`;
    if (!taken.includes(key)) return key;
  }
}

/** The fields a new form starts with: the design's First name, Email, Phone. */
export function starterFields(labels: { first: string; email: string; phone: string }): FormField[] {
  return [
    { key: "first_name", type: "text", label: labels.first, required: true, target: "first_name", options: null },
    { key: "email", type: "email", label: labels.email, required: true, target: "email", options: null },
    { key: "phone", type: "phone", label: labels.phone, required: false, target: "phone", options: null },
  ];
}

export function useForms(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: formKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/forms", { params: { path: where(workspaceId) } })),
  });
}

const one = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, form_id: id });

export function useForm(workspaceId: string, id: string) {
  return useQuery({
    queryKey: formKeys.one(workspaceId, id),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/forms/{form_id}", { params: { path: one(workspaceId, id) } })),
  });
}

/** A form refusal: its code and, for a field, the field's position. */
export class FormRefusal extends ApiError {
  readonly field: number | undefined;

  constructor(status: number, code: string | undefined, field: number | undefined) {
    super(status, code);
    this.name = "FormRefusal";
    this.field = field;
  }
}

function written<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  const detail =
    typeof result.error === "object" && result.error !== null && "detail" in result.error
      ? result.error.detail
      : undefined;
  if (typeof detail === "object" && detail !== null && !Array.isArray(detail) && "code" in detail) {
    const field = "field" in detail && typeof detail.field === "number" ? detail.field : undefined;
    throw new FormRefusal(result.response.status, typeof detail.code === "string" ? detail.code : undefined, field);
  }
  return unwrapWrite(result);
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: formKeys.all(workspaceId) });
}

export function useCreateForm(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Form, ApiError, { body: FormCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      written(
        await api.POST("/v1/workspaces/{tenant_id}/forms", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateForm(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Form, ApiError, { id: string; version: number; changes: FormChanges }>({
    mutationFn: async ({ id, version, changes }) =>
      written(
        await api.PATCH("/v1/workspaces/{tenant_id}/forms/{form_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteForm(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (await api.DELETE("/v1/workspaces/{tenant_id}/forms/{form_id}", { params: { path: one(workspaceId, id) } }))
          .response,
      ),
    onSettled: () => refresh(),
  });
}

export function useSubmissions(workspaceId: string, id: string) {
  return useInfiniteQuery({
    queryKey: formKeys.submissions(workspaceId, id),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: SubmissionPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<SubmissionPage> =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/forms/{form_id}/submissions", {
          params: { path: one(workspaceId, id), query: { limit: 50, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
  });
}

export function useContactConsent(workspaceId: string, contactId: string) {
  return useQuery({
    queryKey: formKeys.consent(workspaceId, contactId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/contacts/{record_id}/consent", {
          params: { path: { tenant_id: workspaceId, record_id: contactId } },
        }),
      ),
  });
}

// --- The hosted page -----------------------------------------------------------------

export function usePublicForm(workspaceId: string, key: string) {
  return useQuery({
    queryKey: ["public-form", workspaceId, key],
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/public/forms/{workspace_id}/{key}", {
          params: { path: { workspace_id: workspaceId, key } },
        }),
      ),
  });
}

export type Answer = string | boolean | null;

/** A refused submission: a rule's code per field key. */
export class AnswersRefused extends ApiError {
  readonly fields: Record<string, string>;

  constructor(fields: Record<string, string>) {
    super(422, "invalid_answers");
    this.name = "AnswersRefused";
    this.fields = fields;
  }
}

function answersRefusal(error: unknown): Record<string, string> | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const detail = error.detail;
  if (typeof detail !== "object" || detail === null || !("fields" in detail)) return undefined;
  const fields = detail.fields;
  if (typeof fields !== "object" || fields === null) return undefined;
  return Object.fromEntries(
    Object.entries(fields).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

export function useSubmitPublicForm(workspaceId: string, key: string) {
  return useMutation<
    { thank_you: string },
    ApiError,
    { answers: Record<string, Answer>; consent: boolean; website: string; attempt: string }
  >({
    mutationFn: async ({ answers, consent, website, attempt }) => {
      const result = await api.POST("/v1/public/forms/{workspace_id}/{key}", {
        params: { path: { workspace_id: workspaceId, key }, header: { "Idempotency-Key": attempt } },
        body: { answers, consent, website },
      });
      if (result.response.ok && result.data !== undefined) return result.data;
      const fields = result.response.status === 422 ? answersRefusal(result.error) : undefined;
      if (fields) throw new AnswersRefused(fields);
      return unwrap(result);
    },
  });
}
