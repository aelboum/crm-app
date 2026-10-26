import { useState } from "react";

import {
  ExportError,
  type ExportKind,
  exportCompanies,
  exportContacts,
  fileDownload,
} from "../api/exportContacts";
import type { ListFilters } from "../api/records";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

type ExportMessage =
  | "running"
  | "done"
  | "notAllowed"
  | "forbidden"
  | "tooLarge"
  | "limited"
  | "waitSeconds"
  | "waitMinutes"
  | "unavailable"
  | "failed"
  | "network";

/** The messages of each kind's export: `contacts.export.*`, `companies.export.*`. */
export function exportMessage(kind: ExportKind, message: ExportMessage): MessageId {
  return `${kind}.export.${message}`;
}

const EXPORTERS: Record<ExportKind, typeof exportContacts> = {
  contacts: exportContacts,
  companies: exportCompanies,
};

/**
 * Exports the current filters as CSV (slices 3E1, 3E2) and saves the file.
 * The button's state comes from `/access`; the server enforces the
 * permission. Failures are reported, never retried automatically.
 */
export function useRecordExport(kind: ExportKind, workspaceId: string) {
  const t = useT();
  const toast = useToast();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const m = (message: ExportMessage) => exportMessage(kind, message);

  /** Seconds as a short wait: "2 minutes", "45 seconds". */
  function waitText(seconds: number): string {
    return seconds < 60
      ? t(m("waitSeconds"), { count: Math.max(1, Math.ceil(seconds)) })
      : t(m("waitMinutes"), { count: Math.ceil(seconds / 60) });
  }

  function explain(failure: unknown): string {
    const status = failure instanceof ExportError ? failure.status : 0;
    const wait = failure instanceof ExportError ? failure.retryAfter : null;
    switch (status) {
      case 0:
        return t(m("network"));
      case 403:
        return t(m("forbidden"));
      case 413:
        return t(m("tooLarge"));
      case 429:
        return wait === null ? t(m("limited")) : `${t(m("limited"))} ${waitText(wait)}`;
      case 503:
        return t(m("unavailable"));
      default:
        return t(m("failed"));
    }
  }

  async function run(filters: ListFilters) {
    if (running) return;
    setRunning(true);
    setError(null);
    try {
      const { blob, fileName } = await EXPORTERS[kind](workspaceId, filters);
      fileDownload.save(blob, fileName);
      toast(t(m("done")));
    } catch (failure) {
      setError(explain(failure));
    } finally {
      setRunning(false);
    }
  }

  return { run, running, error };
}
