import { Download, Upload } from "lucide-react";
import { useId, useState } from "react";

import { ApiError } from "../api/client";
import {
  cancelImport,
  commitImport,
  errorReportUrl,
  type ImportEntity,
  type ImportPreview,
  isActive,
  previewImport,
  resumeImport,
  useImport,
} from "../api/imports";
import { Loading } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Import contacts or companies from a CSV file (decision P3-F). Three
 * steps: choose a file, which the server reads and checks without
 * importing anything; review the mapping, the counts, the first refused
 * rows; then import, following the worker's progress. Rows that duplicate
 * an existing record are skipped, never merged. The file is never stored,
 * and the server keeps the checked rows for 7 days.
 */

const FIELDS: Record<ImportEntity, [string, MessageId][]> = {
  contact: [
    ["first_name", "contact.field.firstName"],
    ["last_name", "contact.field.lastName"],
    ["email", "contact.field.email"],
    ["phone", "contact.field.phone"],
    ["job_title", "contact.field.jobTitle"],
    ["city", "contact.field.city"],
    ["lifecycle_stage", "contact.field.stage"],
  ],
  company: [
    ["name", "company.field.name"],
    ["domain", "company.field.domain"],
    ["website", "company.field.website"],
    ["phone", "company.field.phone"],
    ["industry", "company.field.industry"],
    ["city", "company.field.city"],
    ["country_code", "company.field.country"],
  ],
};

const FAILURES: Partial<Record<string, MessageId>> = {
  file_too_large: "import.error.tooLarge",
  unreadable_file: "import.error.unreadable",
  empty_file: "import.error.noRows",
  no_rows: "import.error.noRows",
  too_many_rows: "import.error.tooManyRows",
  too_many_columns: "import.error.tooManyColumns",
  cell_too_long: "import.error.cellTooLong",
  required_field_unmapped: "import.error.required",
  csv_required: "import.error.unreadable",
  invalid_mapping: "import.error.mapping",
  column_mapped_twice: "import.error.mapping",
  import_in_progress: "import.error.inProgress",
  nothing_to_import: "import.error.nothing",
  import_not_previewed: "import.error.stale",
};

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    const known = error.code ? FAILURES[error.code] : undefined;
    if (known) return known;
    if (error.status === 429) return "import.error.limited";
    if (error.status === 403) return "import.error.forbidden";
    if (error.status === 503) return "import.error.unavailable";
  }
  return "import.error.failed";
}

const CODE_LABEL: Partial<Record<string, MessageId>> = {
  invalid: "import.code.invalid",
  email_or_phone_required: "import.code.emailOrPhone",
  duplicate: "import.code.duplicate",
  skipped: "import.code.duplicate",
  failed: "import.code.failed",
};

const STATUS_LABEL: Record<string, MessageId> = {
  previewed: "import.status.previewed",
  queued: "import.status.queued",
  running: "import.status.running",
  completed: "import.status.completed",
  completed_with_errors: "import.status.completedWithErrors",
  failed: "import.status.failed",
  cancelled: "import.status.cancelled",
  expired: "import.status.expired",
};

type Summary = ImportPreview["summary"];

export function ImportDialog({
  workspaceId,
  entity,
  onClose,
}: {
  workspaceId: string;
  entity: ImportEntity;
  onClose: () => void;
}) {
  const t = useT();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageId | null>(null);
  const [importId, setImportId] = useState<string | null>(null);
  const progress = useImport(workspaceId, importId);
  const summary: Summary | undefined = progress.data ?? preview?.summary;

  async function check(next: File, columns?: string[]) {
    setBusy(true);
    setError(null);
    try {
      const result = await previewImport(workspaceId, entity, next, columns);
      setPreview(result);
      setMapping(
        Object.fromEntries(Object.entries(result.summary.mapping).map(([key, value]) => [key, String(value)])),
      );
    } catch (problem) {
      setPreview(null);
      setError(failure(problem));
    } finally {
      setBusy(false);
    }
  }

  async function act(action: () => Promise<Summary>) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setImportId(result.id);
    } catch (problem) {
      setError(failure(problem));
    } finally {
      setBusy(false);
    }
  }

  const columns = () =>
    Object.entries(mapping)
      .filter(([, position]) => position !== "")
      .map(([name, position]) => `${name}:${position}`);

  const title = t(entity === "contact" ? "import.titleContacts" : "import.titleCompanies");
  const running = importId !== null && summary !== undefined && isActive(summary);

  const actions = (
    <>
      <Button onPress={onClose}>{importId ? t("import.close") : t("confirm.cancel")}</Button>
      {preview && !importId ? (
        <Button
          variant="primary"
          isDisabled={busy || preview.summary.valid_rows === 0}
          onPress={() => void act(() => commitImport(workspaceId, preview.summary.id))}
        >
          {t("import.commit", { count: preview.summary.valid_rows })}
        </Button>
      ) : null}
      {running && !summary.cancel_requested ? (
        <Button variant="destructive" isDisabled={busy} onPress={() => void act(() => cancelImport(workspaceId, importId))}>
          {t("import.cancel")}
        </Button>
      ) : null}
      {importId && summary?.status === "failed" ? (
        <Button variant="primary" isDisabled={busy} onPress={() => void act(() => resumeImport(workspaceId, importId))}>
          {t("import.resume")}
        </Button>
      ) : null}
    </>
  );

  return (
    <Dialog isOpen title={title} onClose={onClose} actions={actions}>
      <div className="import-dialog">
        {error ? (
          <p className="notice error" role="alert">
            {t(error)}
          </p>
        ) : null}
        {importId ? null : (
          <div className="form-field">
            <label className="form-label" htmlFor={fileId}>
              {t("import.file")}
            </label>
            <input
              id={fileId}
              type="file"
              accept=".csv,text/csv"
              className="form-input"
              aria-describedby={`${fileId}-hint`}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null;
                setFile(next);
                if (next) void check(next);
              }}
            />
            <span id={`${fileId}-hint`} className="form-hint">
              {t("import.fileHint")}
            </span>
          </div>
        )}
        {busy && !preview ? <Loading /> : null}
        {preview && !importId ? (
          <>
            <fieldset className="import-mapping">
              <legend className="form-label">{t("import.mapping")}</legend>
              {FIELDS[entity].map(([name, label]) => (
                <div key={name} className="form-field">
                  <label className="form-label" htmlFor={`${fileId}-${name}`}>
                    {t(label)}
                  </label>
                  <select
                    id={`${fileId}-${name}`}
                    className="form-input form-select"
                    value={mapping[name] ?? ""}
                    onChange={(event) => {
                      setMapping((current) => ({ ...current, [name]: event.target.value }));
                    }}
                  >
                    <option value="">{t("import.notImported")}</option>
                    {preview.header.map((column, position) => (
                      <option key={String(position)} value={String(position)}>
                        {column || t("import.column", { number: position + 1 })}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              <Button
                size="sm"
                isDisabled={busy || !file}
                onPress={() => {
                  if (file) void check(file, columns());
                }}
              >
                {t("import.recheck")}
              </Button>
            </fieldset>
            <Counts summary={preview.summary} />
            <RefusedRows summary={preview.summary} workspaceId={workspaceId} />
          </>
        ) : null}
        {importId && summary ? (
          <div className="import-progress">
            <p role="status" aria-live="polite">
              <strong>{t(STATUS_LABEL[summary.status] ?? "import.status.running")}</strong>{" "}
              {t("import.result", {
                created: summary.created_rows,
                skipped: summary.skipped_rows,
                failed: summary.failed_rows,
              })}
            </p>
            {running ? null : <RefusedRows summary={summary} workspaceId={workspaceId} />}
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}

function Counts({ summary }: { summary: Summary }) {
  const t = useT();
  const counts: [MessageId, number][] = [
    ["import.count.total", summary.total_rows],
    ["import.count.valid", summary.valid_rows],
    ["import.count.duplicates", summary.duplicate_rows],
    ["import.count.invalid", summary.invalid_rows],
  ];
  return (
    <dl className="import-counts">
      {counts.map(([label, value]) => (
        <div key={label}>
          <dt>{t(label)}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RefusedRows({ summary, workspaceId }: { summary: Summary; workspaceId: string }) {
  const t = useT();
  if (summary.errors.length === 0) return null;
  return (
    <div className="import-errors">
      <table className="records-table">
        <caption className="sr-only">{t("import.refused")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("import.row")}</th>
            <th scope="col">{t("import.field")}</th>
            <th scope="col">{t("import.problem")}</th>
          </tr>
        </thead>
        <tbody>
          {summary.errors.map((problem, index) => (
            <tr key={`${String(problem.row)}-${String(index)}`}>
              <td>{problem.row}</td>
              <td>{problem.field ?? "—"}</td>
              <td>{t(CODE_LABEL[problem.code] ?? "import.code.invalid")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <a className="text-button" href={errorReportUrl(workspaceId, summary.id)} download>
        <Download size={13} aria-hidden="true" />
        {t("import.errorReport")}
      </a>
    </div>
  );
}

/** The header's Import button: enabled for those `/access` allows. */
export function ImportButton({ allowed, onPress }: { allowed: boolean; onPress: () => void }) {
  const t = useT();
  return allowed ? (
    <Button onPress={onPress}>
      <Upload size={14} aria-hidden="true" />
      {t("records.import")}
    </Button>
  ) : (
    <Button isDisabled aria-label={`${t("records.import")} (${t("import.notAllowed")})`}>
      <Upload size={14} aria-hidden="true" />
      {t("records.import")}
    </Button>
  );
}
