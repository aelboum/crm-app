import { api } from "./client";
import type { ListFilters } from "./records";

/*
 * Contacts and companies CSV export (slices 3E1 and 3E2). The server decides
 * who may export and which rows: this sends the list's current filters and
 * order (no paging) and saves what comes back. Nothing is retried
 * automatically: an export is costly and counts towards a limit of 10 per
 * user per window, kept separately for contacts and for companies.
 */

export type ExportKind = "contacts" | "companies";

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

const SAFE_NAME = /filename="([A-Za-z0-9._-]{1,100})"/;

/** The server's file name when it is a plain, safe one; otherwise a fixed name. */
export function fileNameFrom(disposition: string | null, kind: ExportKind = "contacts"): string {
  const match = disposition ? SAFE_NAME.exec(disposition) : null;
  const name = match?.[1];
  return name && name.endsWith(".csv") && !name.startsWith(".") ? name : `${kind}.csv`;
}

function retryAfterOf(response: Response): number | null {
  const raw = response.headers.get("Retry-After");
  if (raw === null) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

type Exported = { blob: Blob; fileName: string };

function exported(
  kind: ExportKind,
  result: { data?: unknown; response: Response },
): Exported {
  const { response } = result;
  if (!response.ok || !(result.data instanceof Blob)) {
    throw new ExportError(response.status, retryAfterOf(response));
  }
  return { blob: result.data, fileName: fileNameFrom(response.headers.get("Content-Disposition"), kind) };
}

/** The filters both lists share, as the export's query parameters. */
function common(filters: ListFilters) {
  const q = filters.q.trim();
  return {
    sort: filters.sort,
    direction: filters.direction,
    archived: filters.archived,
    ...(q ? { q } : {}),
    ...(filters.owners.length ? { owner: filters.owners } : {}),
  };
}

export async function exportContacts(workspaceId: string, filters: ListFilters): Promise<Exported> {
  let result;
  try {
    result = await api.GET("/v1/workspaces/{tenant_id}/contacts/export.csv", {
      params: {
        path: { tenant_id: workspaceId },
        query: {
          ...common(filters),
          ...(filters.stages.length ? { lifecycle_stage: [...filters.stages] } : {}),
          ...(filters.companyIds.length ? { company_id: filters.companyIds } : {}),
        },
      },
      parseAs: "blob",
    });
  } catch {
    throw new ExportError(0, null);
  }
  return exported("contacts", result);
}

/** The company list's filters only: it has no stage or company filter. */
export async function exportCompanies(workspaceId: string, filters: ListFilters): Promise<Exported> {
  let result;
  try {
    result = await api.GET("/v1/workspaces/{tenant_id}/companies/export.csv", {
      params: { path: { tenant_id: workspaceId }, query: common(filters) },
      parseAs: "blob",
    });
  } catch {
    throw new ExportError(0, null);
  }
  return exported("companies", result);
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
