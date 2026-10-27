import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  amountText,
  type Deal,
  type DealChanges,
  type DealCreate,
  useCreateDeal,
  useUpdateDeal,
} from "../api/opportunities";
import type { Stage } from "../api/pipelines";
import { FieldErrors, newIdempotencyKey } from "../api/records";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { CompanyPicker, type PickedCompany } from "./CompanyPicker";
import type { Option } from "./parts";

/*
 * The design's "New opportunity" dialog (ScreenPipeline.dc.html), here also
 * used for editing. Fields: name (required), value in the deal's currency
 * (the workspace's for a new deal, decision P4-B 2), stage, owner, expected
 * close date, contact and company. The value is checked here as the server
 * checks it, so a value is never rounded; the server decides. A new deal
 * keeps one idempotency key while the dialog is open, so a retried create
 * cannot make a second deal.
 */

type Field = "title" | "amount" | "stage_id" | "owner_user_id" | "expected_close_date";
const FIELDS: readonly string[] = ["title", "amount", "stage_id", "owner_user_id", "expected_close_date"];

const REFUSALS: Record<string, MessageId> = {
  invalid_amount: "deals.error.amount",
  stage_not_found: "deals.error.stale",
  contact_not_found: "deals.error.contact",
  company_not_found: "deals.error.company",
  owner_not_member: "deals.error.owner",
  stale_version: "deals.error.version",
  deal_closed: "deals.error.closed",
  invalid_outcome_transition: "deals.error.version",
};

/** The message for a refused deal change. */
export function refusalOf(error: unknown): MessageId {
  if (error instanceof ApiError) {
    const known = error.code ? REFUSALS[error.code] : undefined;
    if (known) return known;
    if (error.status === 403) return "deals.error.forbidden";
    if (error.status === 404) return "deals.error.gone";
  }
  return "deals.error.failed";
}

export function DealDialog({
  workspaceId,
  deal,
  stages,
  currency,
  owners,
  meId,
  onClose,
  onSaved,
}: {
  workspaceId: string;
  /** The deal being edited, or null for a new one. */
  deal: Deal | null;
  stages: Stage[];
  /** The workspace's currency, for a new deal. */
  currency: string;
  owners: Option[];
  meId: string | undefined;
  onClose: () => void;
  onSaved: (deal: Deal) => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateDeal(workspaceId);
  const update = useUpdateDeal(workspaceId);
  const [key] = useState(newIdempotencyKey);
  const dealCurrency = deal?.currency ?? currency;
  const [values, setValues] = useState({
    title: deal?.title ?? "",
    amount: deal?.amount ?? "",
    stage_id: deal?.stage_id ?? stages[0]?.id ?? "",
    owner_user_id: deal ? (deal.owner_user_id ?? "") : (meId ?? ""),
    expected_close_date: deal?.expected_close_date ?? "",
  });
  const [contact, setContact] = useState<PickedCompany | null>(deal?.contact ?? null);
  const [company, setCompany] = useState<PickedCompany | null>(deal?.company ?? null);
  const [invalid, setInvalid] = useState<Set<Field>>(new Set());
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const pending = create.isPending || update.isPending;
  const closed = deal !== null && deal.outcome !== "open";

  const set = (field: Field, value: string) => {
    setValues((current) => ({ ...current, [field]: value }));
    setInvalid((current) => {
      const next = new Set(current);
      next.delete(field);
      return next;
    });
  };

  function problems(): Set<Field> {
    const found = new Set<Field>();
    if (!values.title.trim()) found.add("title");
    if (values.amount.trim() && amountText(values.amount, dealCurrency) === null) found.add("amount");
    return found;
  }

  function body(): DealCreate {
    return {
      title: values.title.trim(),
      amount: values.amount.trim() ? amountText(values.amount, dealCurrency) : null,
      stage_id: values.stage_id || null,
      owner_user_id: values.owner_user_id || null,
      expected_close_date: values.expected_close_date || null,
      contact_id: contact?.id ?? null,
      company_id: company?.id ?? null,
    };
  }

  /** Only what changed, so an edit never rewrites what it did not touch. */
  function changes(original: Deal): DealChanges {
    const next = body();
    const delta: DealChanges = {};
    if (next.title !== original.title) delta.title = next.title;
    if ((next.amount ?? null) !== original.amount) delta.amount = next.amount ?? null;
    if (next.stage_id && next.stage_id !== original.stage_id) delta.stage_id = next.stage_id;
    if ((next.owner_user_id ?? null) !== original.owner_user_id) delta.owner_user_id = next.owner_user_id ?? null;
    if ((next.expected_close_date ?? null) !== original.expected_close_date) {
      delta.expected_close_date = next.expected_close_date ?? null;
    }
    if ((next.contact_id ?? null) !== original.contact_id) delta.contact_id = next.contact_id ?? null;
    if ((next.company_id ?? null) !== original.company_id) delta.company_id = next.company_id ?? null;
    return delta;
  }

  function fail(error: ApiError) {
    if (error instanceof FieldErrors) {
      setInvalid(new Set(error.fields.filter((f): f is Field => FIELDS.includes(f))));
    }
    if (error.code === "invalid_amount") setInvalid(new Set<Field>(["amount"]));
    setRefusal(refusalOf(error));
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    setRefusal(null);
    const found = problems();
    setInvalid(found);
    if (found.size > 0) return;
    const done = (saved: Deal) => {
      toast(deal ? t("records.saved") : t("deals.created", { title: saved.title }));
      onSaved(saved);
    };
    if (deal) {
      const delta = changes(deal);
      if (Object.keys(delta).length === 0) {
        onClose();
        return;
      }
      update.mutate({ id: deal.id, version: deal.version, changes: delta }, { onSuccess: done, onError: fail });
    } else {
      create.mutate({ body: body(), key }, { onSuccess: done, onError: fail });
    }
  }

  const fieldError = (field: Field): string | null => {
    if (!invalid.has(field)) return null;
    if (field === "title") return t("deals.error.title");
    if (field === "amount") return t("deals.error.amountHint", { currency: dealCurrency });
    return t("records.error.field");
  };

  const described = (field: Field) =>
    fieldError(field) ? { "aria-invalid": true as const, "aria-describedby": `deal-${field}-error` } : {};

  const errorText = (field: Field) =>
    fieldError(field) ? (
      <span id={`deal-${field}-error`} className="form-error">
        {fieldError(field)}
      </span>
    ) : null;

  return (
    <Dialog
      isOpen
      title={deal ? t("deals.edit") : t("deals.new")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="deal-form" isDisabled={pending}>
            {deal ? t("records.saveChanges") : t("deals.create")}
          </Button>
        </>
      }
    >
      <form id="deal-form" className="record-form" onSubmit={submit} noValidate>
        <div className="form-field wide">
          <label htmlFor="deal-title" className="form-label">
            {t("deals.field.title")}
          </label>
          <input
            id="deal-title"
            className="form-input"
            value={values.title}
            maxLength={200}
            required
            onChange={(event) => {
              set("title", event.target.value);
            }}
            {...described("title")}
          />
          {errorText("title")}
        </div>
        <div className="form-field">
          <label htmlFor="deal-amount" className="form-label">
            {t("deals.field.value", { currency: dealCurrency })}
          </label>
          <input
            id="deal-amount"
            className="form-input"
            inputMode="decimal"
            value={values.amount}
            maxLength={20}
            placeholder="0"
            onChange={(event) => {
              set("amount", event.target.value);
            }}
            {...described("amount")}
          />
          {errorText("amount")}
        </div>
        <div className="form-field">
          <label htmlFor="deal-stage" className="form-label">
            {t("deals.field.stage")}
          </label>
          <select
            id="deal-stage"
            className="form-input form-select"
            value={values.stage_id}
            disabled={closed}
            {...(closed ? { "aria-describedby": "deal-stage-hint" } : {})}
            onChange={(event) => {
              set("stage_id", event.target.value);
            }}
          >
            {stages.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
          </select>
          {closed ? (
            <span id="deal-stage-hint" className="form-hint">
              {t("deals.closedStageHint")}
            </span>
          ) : null}
        </div>
        <div className="form-field">
          <label htmlFor="deal-owner" className="form-label">
            {t("records.field.owner")}
          </label>
          <select
            id="deal-owner"
            className="form-input form-select"
            value={values.owner_user_id}
            onChange={(event) => {
              set("owner_user_id", event.target.value);
            }}
          >
            <option value="">{t("records.owner.none")}</option>
            {owners.map((owner) => (
              <option key={owner.id} value={owner.id}>
                {owner.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="deal-close" className="form-label">
            {t("deals.field.close")}
          </label>
          <input
            id="deal-close"
            className="form-input"
            type="date"
            value={values.expected_close_date}
            onChange={(event) => {
              set("expected_close_date", event.target.value);
            }}
          />
        </div>
        <CompanyPicker
          workspaceId={workspaceId}
          kind="contacts"
          id="deal-contact"
          label={t("deals.field.contact")}
          selected={contact}
          onChange={setContact}
        />
        <CompanyPicker
          workspaceId={workspaceId}
          id="deal-company"
          label={t("deals.field.company")}
          selected={company}
          onChange={setCompany}
        />
        <p className="form-hint wide">{t("deals.hint")}</p>
        {refusal ? (
          <p className="notice error wide" role="alert">
            {t(refusal)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
