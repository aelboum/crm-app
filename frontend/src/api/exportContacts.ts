import { api } from "./client";
import type { ListFilters } from "./records";

/*
 * Contacts CSV export (slice 3E). The server decides who may export and
 * which rows: this sends the list's current filters and order (no paging)
 * and saves what comes back. Nothing is retried automatically: an export is
 * costly and counts towards a limit of 10 per user per window.
 */

/** A refused or failed export. Status 0: the request never reached the server. */
export class ExportError extends Error {
  readonly status: number;
  /** Seconds the server asked to wait (429, 503), when it said. */
  readonly retryAfter: number | null;

  constructor(status: number, retryAfter: number | null) {
    super(`export ${String(status)}`);
    this.name = "ExportError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

const FALLBACK_NAME = "contacts.csv";
const SAFE_NAME = /filename="([A-Za-z0-9._-]{1,100})"/;

/** The server's file name when it is a plain, safe one; otherwise a fixed name. */
export function fileNameFrom(disposition: string | null): string {
  const match = disposition ? SAFE_NAME.exec(disposition) : null;
  const name = match?.[1];
  return name && name.endsWith(".csv") && !name.startsWith(".") ? name : FALLBACK_NAME;
}

function retryAfterOf(response: Response): number | null {
  const raw = response.headers.get("Retry-After");
  if (raw === null) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export async function exportContacts(
  workspaceId: string,
  filters: ListFilters,
): Promise<{ blob: Blob; fileName: string }> {
  const q = filters.q.trim();
  let result;
  try {
    result = await api.GET("/v1/workspaces/{tenant_id}/contacts/export.csv", {
      params: {
        path: { tenant_id: workspaceId },
        query: {
          sort: filters.sort,
          direction: filters.direction,
          archived: filters.archived,
          ...(q ? { q } : {}),
          ...(filters.owners.length ? { owner: filters.owners } : {}),
          ...(filters.stages.length ? { lifecycle_stage: [...filters.stages] } : {}),
          ...(filters.companyIds.length ? { company_id: filters.companyIds } : {}),
        },
      },
      parseAs: "blob",
    });
  } catch {
    throw new ExportError(0, null);
  }
  const { response } = result;
  if (!response.ok || !(result.data instanceof Blob)) {
    throw new ExportError(response.status, retryAfterOf(response));
  }
  return { blob: result.data, fileName: fileNameFrom(response.headers.get("Content-Disposition")) };
}

/** Saves a file through a temporary link. Replaced in tests: jsdom does not download. */
export const fileDownload = {
  save(blob: Blob, fileName: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    link.rel = "noopener";
    document.body.append(link);
    link.click();
    link.remove();
    // Give the browser time to start the download before the URL goes.
    setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 30_000);
  },
};
