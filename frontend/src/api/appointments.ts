import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { expectNoContent, ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * Appointments (decision P5-A). Every role reads; Owners, Admins and
 * Members book, change and cancel (`create_appointment`,
 * `update_appointment`); Owners and Admins delete. Times travel as ISO
 * timestamps with their offset and are shown in the viewer's own time zone
 * (P5-A 5); the day, week and month boundaries are computed here.
 */

export type Appointment = components["schemas"]["AppointmentOut"];
export type AppointmentCreate = components["schemas"]["AppointmentIn"];
/** The fields a change may send; whether to allow a conflict is passed beside them. */
export type AppointmentChanges = Omit<components["schemas"]["AppointmentPatch"], "allow_conflict">;
export type Conflict = components["schemas"]["Conflict"];
export type Kind = Appointment["kind"];
export type Status = Appointment["status"];
export const KINDS: readonly Kind[] = ["in_person", "video", "phone"];
/** The design's four statuses, in its order; cancelling is its own action. */
export const STATUSES: readonly Exclude<Status, "cancelled">[] = ["confirmed", "pending", "completed", "no_show"];
/** The booking lengths offered, in minutes. */
export const LENGTHS: readonly number[] = [15, 30, 45, 60, 90, 120];

/** A refusal because the host is busy (409 `appointment_conflict`), with what is in the way. */
export class ConflictRefusal extends ApiError {
  readonly conflicts: Conflict[];

  constructor(conflicts: Conflict[]) {
    super(409, "appointment_conflict");
    this.name = "ConflictRefusal";
    this.conflicts = conflicts;
  }
}

function conflictsOf(error: unknown): Conflict[] | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const detail = error.detail;
  if (typeof detail !== "object" || detail === null || !("conflicts" in detail)) return undefined;
  return Array.isArray(detail.conflicts) ? (detail.conflicts as Conflict[]) : undefined;
}

function written<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok && result.response.status === 409) {
    const conflicts = conflictsOf(result.error);
    if (conflicts) throw new ConflictRefusal(conflicts);
  }
  return unwrapWrite(result);
}

export interface ConflictCheck {
  host: string;
  start: string;
  end: string;
  exclude: string | null;
}

export const appointmentKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "appointments"] as const,
  range: (workspaceId: string, start: string, end: string) =>
    [...appointmentKeys.all(workspaceId), "range", start, end] as const,
  upcoming: (workspaceId: string, contactId: string | null) =>
    [...appointmentKeys.all(workspaceId), "upcoming", contactId] as const,
  conflicts: (workspaceId: string, check: ConflictCheck | null) =>
    [...appointmentKeys.all(workspaceId), "conflicts", check] as const,
};

/** Every appointment overlapping `[start, end)` (at most 42 days), earliest first. */
export function useAppointments(workspaceId: string, start: Date, end: Date) {
  const from = start.toISOString();
  const to = end.toISOString();
  return useQuery({
    queryKey: appointmentKeys.range(workspaceId, from, to),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/appointments", {
          params: { path: where(workspaceId), query: { start: from, end: to } },
        }),
      ),
  });
}

export function useAppointment(workspaceId: string, id: string | null) {
  return useQuery({
    queryKey: [...appointmentKeys.all(workspaceId), "one", id] as const,
    enabled: id !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/appointments/{appointment_id}", {
          params: { path: one(workspaceId, id ?? "") },
        }),
      ),
  });
}

/** What has not ended yet, soonest first: "Up next", or one contact's. */
export function useUpcoming(workspaceId: string, contactId: string | null = null, limit = 5) {
  return useQuery({
    queryKey: appointmentKeys.upcoming(workspaceId, contactId),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/appointments/upcoming", {
          params: { path: where(workspaceId), query: { limit, ...(contactId ? { contact_id: [contactId] } : {}) } },
        }),
      ).items,
  });
}

/** The booking dialog's live check (P5-A 4); off until the times make sense. */
export function useConflicts(workspaceId: string, check: ConflictCheck | null) {
  return useQuery({
    queryKey: appointmentKeys.conflicts(workspaceId, check),
    enabled: check !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/appointments/conflicts", {
          params: {
            path: where(workspaceId),
            query: {
              host_user_id: check?.host ?? "",
              starts_at: check?.start ?? "",
              ends_at: check?.end ?? "",
              ...(check?.exclude ? { exclude_id: check.exclude } : {}),
            },
          },
        }),
      ).conflicts,
  });
}

function useRefresh(workspaceId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: appointmentKeys.all(workspaceId) });
}

const one = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, appointment_id: id });

export function useCreateAppointment(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<Appointment, ApiError, { body: AppointmentCreate; key: string }>({
    mutationFn: async ({ body, key }) =>
      written(
        await api.POST("/v1/workspaces/{tenant_id}/appointments", {
          params: { path: where(workspaceId), header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: () => refresh(),
  });
}

export function useUpdateAppointment(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<
    Appointment,
    ApiError,
    { id: string; version: number; changes: AppointmentChanges; allowConflict?: boolean }
  >({
    mutationFn: async ({ id, version, changes, allowConflict = false }) =>
      written(
        await api.PATCH("/v1/workspaces/{tenant_id}/appointments/{appointment_id}", {
          params: { path: one(workspaceId, id), header: ifMatch(version) },
          body: { ...changes, allow_conflict: allowConflict },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useDeleteAppointment(workspaceId: string) {
  const refresh = useRefresh(workspaceId);
  return useMutation<null, ApiError, { id: string }>({
    mutationFn: async ({ id }) =>
      expectNoContent(
        (
          await api.DELETE("/v1/workspaces/{tenant_id}/appointments/{appointment_id}", {
            params: { path: one(workspaceId, id) },
          })
        ).response,
      ),
    onSettled: () => refresh(),
  });
}

// --- Days, weeks and months in the viewer's time zone -------------------------------

export type View = "day" | "week" | "month";

export function startOfDay(date: Date): Date {
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return day;
}

/** `days` calendar days later, at the same local time (safe across DST changes). */
export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** The Monday starting the week of `date`, at midnight (the design's weeks run Mon-Sun). */
export function startOfWeek(date: Date): Date {
  const day = startOfDay(date);
  return addDays(day, -((day.getDay() + 6) % 7));
}

/** The days a view shows: one, seven, or the month's whole weeks (28 to 42). */
export function viewDays(view: View, anchor: Date): Date[] {
  if (view === "day") return [startOfDay(anchor)];
  if (view === "week") {
    const monday = startOfWeek(anchor);
    return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  }
  const start = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const days = Math.round((last.getTime() - start.getTime()) / 86_400_000) + 1;
  return Array.from({ length: Math.ceil(days / 7) * 7 }, (_, i) => addDays(start, i));
}

/** The previous or next day, week or month. */
export function step(view: View, anchor: Date, direction: 1 | -1): Date {
  if (view === "day") return addDays(anchor, direction);
  if (view === "week") return addDays(anchor, 7 * direction);
  return new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1);
}

export function sameDay(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}

/** Minutes from the start of `day` to `moment`, clamped to the day. */
export function minutesInto(day: Date, moment: Date): number {
  const minutes = (moment.getTime() - day.getTime()) / 60_000;
  return Math.max(0, Math.min(24 * 60, minutes));
}

/** The appointments that touch `day`. */
export function onDay(items: Appointment[], day: Date): Appointment[] {
  const end = addDays(day, 1);
  return items.filter((a) => new Date(a.starts_at) < end && new Date(a.ends_at) > day);
}

export interface Placed {
  appointment: Appointment;
  lane: number;
  lanes: number;
}

/** Side-by-side lanes for overlapping appointments (the design's layout). */
export function lanes(items: Appointment[]): Placed[] {
  const times = (a: Appointment) => [new Date(a.starts_at).getTime(), new Date(a.ends_at).getTime()] as const;
  const sorted = [...items].sort((a, b) => times(a)[0] - times(b)[0] || a.id.localeCompare(b.id));
  const ends: number[] = [];
  const placed = sorted.map((appointment) => {
    const [start, end] = times(appointment);
    let lane = ends.findIndex((free) => free <= start);
    if (lane < 0) {
      lane = ends.length;
      ends.push(0);
    }
    ends[lane] = end;
    return { appointment, lane, lanes: 1 };
  });
  return placed.map((p) => {
    const [start, end] = times(p.appointment);
    const overlapping = placed.filter((o) => times(o.appointment)[0] < end && times(o.appointment)[1] > start);
    return { ...p, lanes: Math.max(...overlapping.map((o) => o.lane + 1)) };
  });
}

/** A `datetime-local` value for an instant, in local time. */
export function localInput(value: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(value.getFullYear())}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

/** The viewer's time zone, named in the header (P5-A 5). */
export function timeZoneName(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}
