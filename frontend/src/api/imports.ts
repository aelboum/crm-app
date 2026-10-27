import { useQuery } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { useRefresh, where } from "./records";
import type { components } from "./schema";

/*
 * CSV imports (decision P3-F). Owners and Admins only (`import_records` in
 * `/access`); the server enforces it. The file goes up as the request body
 * itself and is never stored. A preview stages the rows; committing queues
 * the worker, whose progress `useImport` polls until the import finishes.
 */

export type ImportEntity = "contact" | "company";
export type ImportSummary = components["schemas"]["ImportSummary"];
export type ImportPreview = components["schemas"]["ImportPreview"];

const ACTIVE = new Set(["queued", "running"]);

export function isActive(summary: ImportSummary | undefined): boolean {
  return summary !== undefined && ACTIVE.has(summary.status);
}

function refused(response: Response, error: unknown): ApiError {
  const detail = typeof error === "object" && error !== null && "detail" in error ? error.detail : undefined;
  const code =
    typeof detail === "object" && detail !== null && "code" in detail && typeof detail.code === "string"
      ? detail.code
      : undefined;
  return new ApiError(response.status, code);
}

/** Read and stage a file; `columns` (`field:position`) overrides the proposed mapping. */
export async function previewImport(
  workspaceId: string,
  entity: ImportEntity,
  file: Blob,
  columns?: string[],
): Promise<ImportPreview> {
  const result = await api.POST("/v1/workspaces/{tenant_id}/imports", {
    params: { path: where(workspaceId), query: { entity, ...(columns?.length ? { column: columns } : {}) } },
    // The file itself is the body, sent as it is.
    body: file as unknown as string,
    bodySerializer: (body: unknown) => body as BodyInit,
    headers: { "Content-Type": "text/csv" },
  });
  if (result.response.ok && result.data) return result.data;
  throw refused(result.response, result.error);
}

const item = (workspaceId: string, id: string) => ({ tenant_id: workspaceId, import_id: id });

async function act(workspaceId: string, id: string, verb: "commit" | "cancel" | "resume") {
  const params = { params: { path: item(workspaceId, id) } };
  const result =
    verb === "commit"
      ? await api.POST("/v1/workspaces/{tenant_id}/imports/{import_id}/commit", params)
      : verb === "cancel"
        ? await api.POST("/v1/workspaces/{tenant_id}/imports/{import_id}/cancel", params)
        : await api.POST("/v1/workspaces/{tenant_id}/imports/{import_id}/resume", params);
  if (result.response.ok && result.data) return result.data;
  throw refused(result.response, result.error);
}

export const commitImport = (workspaceId: string, id: string) => act(workspaceId, id, "commit");
export const cancelImport = (workspaceId: string, id: string) => act(workspaceId, id, "cancel");
export const resumeImport = (workspaceId: string, id: string) => act(workspaceId, id, "resume");

/** One import, polled every two seconds while it is queued or running. */
export function useImport(workspaceId: string, id: string | null) {
  const refresh = useRefresh(workspaceId);
  return useQuery({
    queryKey: ["workspace", workspaceId, "imports", id ?? ""],
    enabled: id !== null,
    refetchInterval: (query) => (isActive(query.state.data) ? 2000 : false),
    queryFn: async () => {
      const summary = unwrap(
        await api.GET("/v1/workspaces/{tenant_id}/imports/{import_id}", {
          params: { path: item(workspaceId, id ?? "") },
        }),
      );
      // New records appear in the lists as the import creates them.
      if (summary.created_rows > 0) void refresh();
      return summary;
    },
  });
}

/** The error report's address: row number, field and code, never a value. */
export function errorReportUrl(workspaceId: string, id: string): string {
  return `/v1/workspaces/${encodeURIComponent(workspaceId)}/imports/${encodeURIComponent(id)}/errors.csv`;
}
