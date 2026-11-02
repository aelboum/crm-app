import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { ExportError, fileNameFrom } from "./exportContacts";
import { where } from "./records";
import type { components } from "./schema";

/*
 * Reports (decision P10-A). Each report has its own endpoint and the read
 * permission of the records it counts, so each card loads and fails alone.
 * A period is two calendar days in the workspace's time zone, both
 * included.
 */

export type ContactReport = components["schemas"]["ContactReport"];
export type DealReport = components["schemas"]["DealReport"];
export type TaskReport = components["schemas"]["TaskReport"];
export type AppointmentReport = components["schemas"]["AppointmentReport"];

export interface Period {
  start: string;
  end: string;
}

export const MAX_DAYS = 366;

const reportKeys = {
  one: (workspaceId: string, kind: string, period: Period) =>
    [
      "workspace",
      workspaceId,
      "reports",
      kind,
      period.start,
      period.end,
    ] as const,
};

export function useContactReport(workspaceId: string, period: Period) {
  return useQuery({
    queryKey: reportKeys.one(workspaceId, "contacts", period),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/reports/contacts", {
          params: { path: where(workspaceId), query: period },
        }),
      ),
  });
}

export function useDealReport(workspaceId: string, period: Period) {
  return useQuery({
    queryKey: reportKeys.one(workspaceId, "deals", period),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/reports/deals", {
          params: { path: where(workspaceId), query: period },
        }),
      ),
  });
}

export function useTaskReport(workspaceId: string, period: Period) {
  return useQuery({
    queryKey: reportKeys.one(workspaceId, "tasks", period),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/reports/tasks", {
          params: { path: where(workspaceId), query: period },
        }),
      ),
  });
}

export function useAppointmentReport(workspaceId: string, period: Period) {
  return useQuery({
    queryKey: reportKeys.one(workspaceId, "appointments", period),
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/reports/appointments", {
          params: { path: where(workspaceId), query: period },
        }),
      ),
  });
}

/*
 * A report as CSV (decision P10-B): the card's figures as rows, with the
 * report's own permission. Saved through `fileDownload`.
 */
export type ReportKind = "contacts" | "deals" | "tasks" | "appointments";

export async function exportReport(
  workspaceId: string,
  kind: ReportKind,
  period: Period,
): Promise<{ blob: Blob; fileName: string }> {
  const path = `/v1/workspaces/{tenant_id}/reports/${kind}/export.csv` as const;
  let result;
  try {
    result = await api.GET(path, {
      params: { path: where(workspaceId), query: period },
      parseAs: "blob",
    });
  } catch {
    throw new ExportError(0, null);
  }
  const { response } = result;
  if (!response.ok || !(result.data instanceof Blob)) {
    throw new ExportError(response.status, null);
  }
  const fallback = `report-${kind}-${period.start}.csv`;
  const name = fileNameFrom(
    response.headers.get("Content-Disposition"),
    "contacts",
  );
  return {
    blob: result.data,
    fileName: name === "contacts.csv" ? fallback : name,
  };
}

/** Today's date (YYYY-MM-DD) in `timeZone`, falling back to the browser's. */
export function todayIn(
  timeZone: string | undefined,
  now: Date = new Date(),
): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(now);
  } catch {
    return new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(now);
  }
}

/** The day `days` before `day` (both YYYY-MM-DD), by calendar. */
export function daysBefore(day: string, days: number): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const date = new Date(Date.UTC(y, m - 1, d - days));
  return date.toISOString().slice(0, 10);
}

/** Days from `start` to `end`, both included. */
export function daysIn(period: Period): number {
  const ms =
    Date.parse(`${period.end}T00:00:00Z`) -
    Date.parse(`${period.start}T00:00:00Z`);
  return Math.round(ms / 86_400_000) + 1;
}
