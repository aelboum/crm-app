import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import { useContactConsent } from "../api/forms";
import { type EmailStatus, useEmailStatus, useRecordConsent, useWithdrawConsent } from "../api/suppression";
import { LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { REASON_LABEL } from "../pages/SuppressionSettings";
import { ownerLabel, When } from "./parts";

/*
 * A contact's email consent (decisions P7-A 7, P7-B 10): its current
 * status (suppressed, consent given, withdrawn or none) and every record,
 * newest first: given on a form, recorded or withdrawn by a member. Records
 * are evidence and never change. Members who may update the contact record
 * consent with the exact wording, or withdraw it, which also suppresses the
 * address. Single opt-in from a web form is unverified, and the section
 * says so rather than implying more.
 */

type T = ReturnType<typeof useT>;

function statusLine(t: T, status: EmailStatus): [Tone, string] {
  if (!status.has_email) return ["neutral", t("consent.status.noEmail")];
  if (status.suppression) {
    return ["risk", t("consent.status.suppressed", { reason: t(REASON_LABEL[status.suppression.reason]) })];
  }
  if (status.consent === "granted") return ["success", t("consent.status.allowed")];
  if (status.consent === "withdrawn") return ["pending", t("consent.status.withdrawn")];
  return ["neutral", t("consent.status.none")];
}

function failure(error: unknown, field: "wording" | "note"): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "contact_has_no_email") return "consent.error.noEmail";
    if (error.status === 422) return field === "wording" ? "consent.error.wording" : "consent.error.note";
  }
  return "consent.error.failed";
}

export function ConsentSection({
  workspaceId,
  contactId,
  meId,
  canUpdate,
}: {
  workspaceId: string;
  contactId: string;
  meId: string | undefined;
  canUpdate: boolean;
}) {
  const t = useT();
  const consent = useContactConsent(workspaceId, contactId);
  const status = useEmailStatus(workspaceId, contactId);
  const [dialog, setDialog] = useState<"record" | "withdraw" | null>(null);
  const items = consent.data?.items ?? [];
  const [tone, line]: [Tone, string] = status.data ? statusLine(t, status.data) : ["neutral", ""];
  return (
    <section className="drawer-section" aria-labelledby="contact-consent-title">
      <h2 id="contact-consent-title" className="drawer-section-title">
        {t("consent.title")}
      </h2>
      {status.isError ? <LoadError error={status.error} onRetry={() => void status.refetch()} /> : null}
      {status.data ? (
        <p className="consent-status">
          <Badge tone={tone}>{line}</Badge>
        </p>
      ) : null}
      {canUpdate && status.data?.has_email ? (
        <div className="consent-actions">
          <Button
            size="sm"
            onPress={() => {
              setDialog("record");
            }}
          >
            {t("consent.record")}
          </Button>
          {status.data.consent !== "withdrawn" || !status.data.suppression ? (
            <Button
              size="sm"
              variant="destructive"
              onPress={() => {
                setDialog("withdraw");
              }}
            >
              {t("consent.withdraw")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {consent.isError ? <LoadError error={consent.error} onRetry={() => void consent.refetch()} /> : null}
      {items.length ? (
        <ul className="consent-list">
          {items.map((record) => (
            <li key={record.id} className="consent-item">
              <span className="consent-head">
                {t(record.status === "granted" ? "consent.granted" : "consent.withdrawn")} ·{" "}
                <When value={record.recorded_at} />
              </span>
              <span className="consent-source">
                {record.method === "manual"
                  ? t("consent.byMember", { who: ownerLabel(t, record.recorded_by_user_id, meId) })
                  : record.form_name
                    ? t("consent.viaForm", { name: record.form_name })
                    : t("consent.viaDeletedForm")}
              </span>
              {record.wording ? (
                record.status === "granted" ? (
                  <q className="consent-wording">{record.wording}</q>
                ) : (
                  <span className="consent-wording">{record.wording}</span>
                )
              ) : null}
            </li>
          ))}
        </ul>
      ) : consent.isPending ? null : (
        <p className="muted">{t("consent.none")}</p>
      )}
      {items.some((record) => record.method === "web_form") ? (
        <p className="form-hint">{t("consent.unverified")}</p>
      ) : null}
      {dialog ? (
        <ConsentDialog
          workspaceId={workspaceId}
          contactId={contactId}
          kind={dialog}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
    </section>
  );
}

function ConsentDialog({
  workspaceId,
  contactId,
  kind,
  onClose,
}: {
  workspaceId: string;
  contactId: string;
  kind: "record" | "withdraw";
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const record = useRecordConsent(workspaceId, contactId);
  const withdraw = useWithdrawConsent(workspaceId, contactId);
  const [text, setText] = useState("");
  const [error, setError] = useState<MessageId | null>(null);
  const recording = kind === "record";
  const busy = record.isPending || withdraw.isPending;

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (recording) {
      if (!value) {
        setError("consent.error.wording");
        return;
      }
      record.mutate(
        { wording: value },
        {
          onSuccess: () => {
            toast(t("consent.recorded"));
            onClose();
          },
          onError: (problem) => {
            setError(failure(problem, "wording"));
          },
        },
      );
      return;
    }
    withdraw.mutate(
      { note: value || null },
      {
        onSuccess: (status) => {
          toast(t(status.suppression ? "consent.withdrawnToast" : "consent.withdrawnNoEmail"));
          onClose();
        },
        onError: (problem) => {
          setError(failure(problem, "note"));
        },
      },
    );
  };

  const fieldId = recording ? "consent-wording" : "consent-note";
  return (
    <Dialog
      isOpen
      title={t(recording ? "consent.recordTitle" : "consent.withdrawTitle")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button
            variant={recording ? "primary" : "destructive"}
            type="submit"
            form="consent-form"
            isDisabled={busy}
          >
            {t(recording ? "consent.record" : "consent.withdraw")}
          </Button>
        </>
      }
    >
      <form id="consent-form" className="record-form" onSubmit={submit} noValidate>
        <p className="form-field wide form-hint" id={`${fieldId}-hint`}>
          {t(recording ? "consent.recordHint" : "consent.withdrawHint")}
        </p>
        <div className="form-field wide">
          <label htmlFor={fieldId} className="form-label">
            {t(recording ? "consent.wording" : "consent.note")}
          </label>
          <textarea
            id={fieldId}
            className="form-input form-textarea"
            rows={3}
            maxLength={500}
            value={text}
            aria-describedby={`${fieldId}-hint`}
            aria-invalid={error ? true : undefined}
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
        </div>
        {error ? (
          <p className="notice error form-field wide" role="alert">
            {t(error)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
