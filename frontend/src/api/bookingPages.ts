import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { appointmentKeys } from "./appointments";
import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Booking pages (decision P5-C). Every role reads them
 * (`read_booking_pages`); Owners and Admins create, edit, publish and delete
 * them (`manage_booking_pages`). The hosted page (`/app/b/<workspace>/<key>`)
 * and the visitor's own link (`/app/b/<workspace>/manage#<token>`) talk to
 * the public routes without a session; the token travels in a body, never
 * in an address the server sees.
 */

export type BookingPage = components["schemas"]["BookingPageOut"];
export type BookingPageCreate = components["schemas"]["BookingPageIn"];
export type BookingPageChanges = components["schemas"]["BookingPagePatch"];
export type PublicBookingPage = components["schemas"]["PublicBookingPage"];
export type BookingView = components["schemas"]["BookingView"];
export type Booked = components["schemas"]["Booked"];
/** What the visitor gives (P5-C 1); the body schema is inline in the OpenAPI document. */
export interface Visitor {
  first_name: string;
  last_name: string | null;
  email: string;
  phone: string | null;
  message: string | null;
}

export const LENGTHS = [15, 30, 45, 60, 90, 120] as const;
export const STEPS = [15, 30, 60] as const;
/** The notice choices, in minutes: none, 1 hour, 4 hours, 1 day, 2 days, 7 days. */
export const NOTICES = [0, 60, 240, 1440, 2880, 10080] as const;
export const HORIZON_MAX = 90;
export const MAX_PAGES = 50;

export const bookingPageKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "booking-pages"] as const,
};

/** The hosted page's address for a booking page. */
export function bookingPath(workspaceId: string, key: string): string {
  return `/app/b/${workspaceId}/${key}`;
}

/** The visitor's private link: the token stays in the fragment. */
export function managePath(workspaceId: string, token: string): string {
  return `/app/b/${workspaceId}/manage#${token}`;
}

export function useBookingPages(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: bookingPageKeys.all(workspaceId),
    enabled,
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/booking-pages", { params: { path: where(workspaceId) } })),
  });
}

const one = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, page_id: id });

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: bookingPageKeys.all(workspaceId) });
}

export function useCreateBookingPage(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<BookingPage, ApiError, { body: BookingPageCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/booking-pages", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateBookingPage(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<BookingPage, ApiError, { id: string; version: number; changes: BookingPageChanges }>({
    mutationFn: async ({ id, version, changes }) =>
      unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/booking-pages/{page_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: changes,
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteBookingPage(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  const client = useQueryClient();
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/booking-pages/{page_id}", {
            params: { path: one(workspaceId, id) },
          })
        ).response,
      ),
    onSettled: async () => {
      await refresh();
      // Appointments it booked no longer name it.
      await client.invalidateQueries({ queryKey: appointmentKeys.all(workspaceId) });
    },
  });
}

// --- The hosted page -----------------------------------------------------------------

export function usePublicBookingPage(workspaceId: string, key: string) {
  return useQuery({
    queryKey: ["public-booking", workspaceId, key],
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/public/booking-pages/{workspace_id}/{key}", {
          params: { path: { workspace_id: workspaceId, key } },
        }),
      ),
  });
}

export function useFreeTimes(workspaceId: string, key: string, start: Date, end: Date, enabled = true) {
  return useQuery({
    queryKey: ["public-booking", workspaceId, key, "times", start.toISOString(), end.toISOString()],
    enabled,
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/public/booking-pages/{workspace_id}/{key}/times", {
          params: {
            path: { workspace_id: workspaceId, key },
            query: { start: start.toISOString(), end: end.toISOString() },
          },
        }),
      ).times,
  });
}

/** Refused details: a rule per field name. */
export class VisitorRefused extends ApiError {
  readonly fields: Record<string, string>;

  constructor(fields: Record<string, string>) {
    super(422, "invalid_visitor");
    this.name = "VisitorRefused";
    this.fields = fields;
  }
}

function visitorRefusal(error: unknown): Record<string, string> | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const detail = error.detail;
  if (typeof detail !== "object" || detail === null || !("fields" in detail)) return undefined;
  const fields = detail.fields;
  if (typeof fields !== "object" || fields === null) return undefined;
  return Object.fromEntries(
    Object.entries(fields).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

export function useBook(workspaceId: string, key: string) {
  const client = useQueryClient();
  return useMutation<Booked, ApiError, { startsAt: string; visitor: Visitor; website: string; attempt: string }>({
    mutationFn: async ({ startsAt, visitor, website, attempt }) => {
      const result = await api.POST("/v1/public/booking-pages/{workspace_id}/{key}", {
        params: { path: { workspace_id: workspaceId, key }, header: { "Idempotency-Key": attempt } },
        body: { ...visitor, starts_at: startsAt, website },
      });
      if (result.response.ok && result.data !== undefined) return result.data;
      const fields = result.response.status === 422 ? visitorRefusal(result.error) : undefined;
      if (fields) throw new VisitorRefused(fields);
      return unwrap(result);
    },
    onError: (error) => {
      // A time taken meanwhile: show the times as they are now.
      if (error.code === "time_unavailable") {
        void client.invalidateQueries({ queryKey: ["public-booking", workspaceId, key, "times"] });
      }
    },
  });
}

export function useVisitorBooking(workspaceId: string, token: string) {
  return useQuery({
    queryKey: ["visitor-booking", workspaceId, token],
    enabled: token !== "",
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.POST("/v1/public/bookings/{workspace_id}/view", {
          params: { path: { workspace_id: workspaceId } },
          body: { token },
        }),
      ),
  });
}

export function useCancelVisitorBooking(workspaceId: string, token: string) {
  const client = useQueryClient();
  return useMutation<BookingView, ApiError>({
    mutationFn: async () =>
      unwrap(
        await api.POST("/v1/public/bookings/{workspace_id}/cancel", {
          params: { path: { workspace_id: workspaceId } },
          body: { token },
        }),
      ),
    onSuccess: (view) => {
      client.setQueryData(["visitor-booking", workspaceId, token], view);
    },
  });
}
