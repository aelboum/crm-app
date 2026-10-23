import { type SyntheticEvent, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { useMe, useMembers } from "../api/queries";
import {
  type Contact,
  type ContactCreate,
  type ContactUpdate,
  DuplicateError,
  FieldErrors,
  NO_FILTERS,
  newIdempotencyKey,
  STAGES,
  type Stage,
  useCompanyList,
  useCreateContact,
  USER_SOURCES,
  useUpdateContact,
} from "../api/records";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ownerOptions, stageLabel } from "./parts";

/*
 * New and edit contact (ScreenContacts.dc.html L224-247): 560 px, two
 * columns. Fields follow decision P3-A: stage and source are fixed lists,
 * and a contact needs an email or a phone number. Tags are not part of
 * slice 3A, so the design's tag pills are left out.
 */

type Field =
  | "first_name"
  | "last_name"
  | "email"
  | "phone"
  | "job_title"
  | "city"
  | "company_id"
  | "lifecycle_stage"
  | "source"
  | "owner_user_id";

type Values = Record<Field, string>;

const FIELDS: Field[] = [
  "first_name",
  "last_name",
  "email",
  "phone",
  "job_title",
  "city",
  "company_id",
  "lifecycle_stage",
  "source",
  "owner_user_id",
];

const SOURCE_LABEL: Record<string, MessageId> = {
  manual: "source.manual",
  import: "source.import",
  form: "source.form",
  referral: "source.referral",
  other: "source.other",
};

export function sourceLabel(t: ReturnType<typeof useT>, source: string): string {
  const id = SOURCE_LABEL[source];
  return id ? t(id) : source;
}

function valuesOf(contact: Contact | null): Values {
  return {
    first_name: contact?.first_name ?? "",
    last_name: contact?.last_name ?? "",
    email: contact?.email ?? "",
    phone: contact?.phone ?? "",
    job_title: contact?.job_title ?? "",
    city: contact?.city ?? "",
    company_id: contact?.company_id ?? "",
    lifecycle_stage: contact?.lifecycle_stage ?? "lead",
    source: contact?.source ?? "manual",
    owner_user_id: contact?.owner_user_id ?? "",
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

function refusalMessage(error: ApiError): MessageId {
  switch (error.code) {
    case "duplicate_email":
      return "contact.error.duplicate";
    case "stale_version":
      return "records.error.stale";
    case "company_not_found":
      return "contact.error.company";
    case "owner_not_member":
      return "records.error.owner";
    case "email_or_phone_required":
      return "contact.error.emailOrPhone";
    case "conflict":
      return "records.error.conflict";
    default:
      return error.status === 403 ? "records.error.denied" : "records.error.generic";
  }
}

export function ContactDialog({
  workspaceId,
  contact,
  onClose,
  onSaved,
  onOpenExisting,
}: {
  workspaceId: string;
  /** The contact to edit, or null to create one. */
  contact: Contact | null;
  onClose: () => void;
  onSaved: (saved: Contact) => void;
  onOpenExisting: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const companies = useCompanyList(workspaceId, NO_FILTERS);
  const create = useCreateContact(workspaceId);
  const update = useUpdateContact(workspaceId);
  const [values, setValues] = useState<Values>(() => valuesOf(contact));
  const [invalid, setInvalid] = useState<Set<Field>>(new Set());
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  // One key per dialog: retrying after a network failure cannot create twice.
  const [key] = useState(newIdempotencyKey);
  const meId = me.data?.user_id;
  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const companyOptions = useMemo(() => {
    const list = (companies.data?.pages ?? []).flatMap((page) => page.items);
    const current = contact?.company;
    return current && !list.some((c) => c.id === current.id)
      ? [{ id: current.id, name: current.name }, ...list]
      : list;
  }, [companies.data, contact]);
  const pending = create.isPending || update.isPending;

  const set = (field: Field) => (event: { target: { value: string } }) => {
    setValues((prev) => ({ ...prev, [field]: event.target.value }));
    setInvalid((prev) => {
      const next = new Set(prev);
      next.delete(field);
      if (field === "email" || field === "phone") {
        next.delete("email");
        next.delete("phone");
      }
      return next;
    });
  };

  function localProblems(): Set<Field> {
    const problems = new Set<Field>();
    if (!values.first_name.trim()) problems.add("first_name");
    if (!values.email.trim() && !values.phone.trim()) {
      problems.add("email");
      problems.add("phone");
    }
    return problems;
  }

  function body(): ContactCreate {
    return {
      first_name: values.first_name.trim(),
      last_name: orNull(values.last_name),
      email: orNull(values.email),
      phone: orNull(values.phone),
      job_title: orNull(values.job_title),
      city: orNull(values.city),
      company_id: orNull(values.company_id),
      lifecycle_stage: values.lifecycle_stage,
      source: values.source,
      owner_user_id: orNull(values.owner_user_id),
    };
  }

  /** Only the fields that changed, so a PATCH never rewrites what it did not touch. */
  function changes(original: Contact): ContactUpdate {
    const next = body();
    const before = valuesOf(original);
    const changed: ContactUpdate = {};
    for (const field of FIELDS) {
      if ((values[field].trim() || "") !== (before[field].trim() || "")) {
        Object.assign(changed, { [field]: next[field] });
      }
    }
    return changed;
  }

  function fail(error: ApiError) {
    if (error instanceof FieldErrors) {
      setInvalid(new Set(error.fields.filter((f): f is Field => FIELDS.includes(f as Field))));
    }
    setRefusal(error);
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    setRefusal(null);
    const problems = localProblems();
    setInvalid(problems);
    if (problems.size > 0) return;
    const done = (saved: Contact) => {
      toast(contact ? t("records.saved") : t("contact.created", { name: saved.first_name }));
      onSaved(saved);
    };
    if (contact) {
      const delta = changes(contact);
      if (Object.keys(delta).length === 0) {
        onClose();
        return;
      }
      update.mutate({ id: contact.id, version: contact.version, changes: delta }, { onSuccess: done, onError: fail });
    } else {
      create.mutate({ body: body(), key }, { onSuccess: done, onError: fail });
    }
  }

  const error = (field: Field): string | null => {
    if (!invalid.has(field)) return null;
    if (field === "first_name") return t("contact.error.firstName");
    if (field === "email" || field === "phone") {
      return refusal instanceof FieldErrors ? t("records.error.field") : t("contact.error.emailOrPhone");
    }
    return t("records.error.field");
  };

  const input = (field: Field, label: string, options: { type?: string; required?: boolean; wide?: boolean } = {}) => {
    const message = error(field);
    const id = `contact-${field}`;
    return (
      <div className={options.wide ? "form-field wide" : "form-field"}>
        <label className="form-label" htmlFor={id}>
          {label}
          {options.required ? <span className="required"> *</span> : null}
        </label>
        <input
          id={id}
          className={message ? "form-input invalid" : "form-input"}
          type={options.type ?? "text"}
          value={values[field]}
          onChange={set(field)}
          aria-invalid={message ? true : undefined}
          aria-describedby={message ? `${id}-error` : undefined}
          autoComplete="off"
        />
        {message ? (
          <span id={`${id}-error`} className="form-error">
            {message}
          </span>
        ) : null}
      </div>
    );
  };

  const select = (field: Field, label: string, choices: { id: string; label: string }[]) => {
    const id = `contact-${field}`;
    const message = error(field);
    return (
      <div className="form-field">
        <label className="form-label" htmlFor={id}>
          {label}
        </label>
        <select
          id={id}
          className={message ? "form-input form-select invalid" : "form-input form-select"}
          value={values[field]}
          onChange={set(field)}
          aria-invalid={message ? true : undefined}
        >
          {choices.map((choice) => (
            <option key={choice.id} value={choice.id}>
              {choice.label}
            </option>
          ))}
        </select>
        {message ? <span className="form-error">{message}</span> : null}
      </div>
    );
  };

  const duplicateOf = refusal instanceof DuplicateError ? refusal.existingId : undefined;

  return (
    <Dialog
      isOpen
      title={contact ? t("contact.edit") : t("contact.new")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="contact-form" isDisabled={pending}>
            {contact ? t("records.saveChanges") : t("contact.create")}
          </Button>
        </>
      }
    >
      <form id="contact-form" className="record-form" onSubmit={submit} noValidate>
        {input("first_name", t("contact.field.firstName"), { required: true })}
        {input("last_name", t("contact.field.lastName"))}
        {input("email", t("contact.field.email"), { type: "email" })}
        {input("phone", t("contact.field.phone"), { type: "tel" })}
        {input("job_title", t("contact.field.jobTitle"))}
        {input("city", t("contact.field.city"))}
        {select("company_id", t("contact.field.company"), [
          { id: "", label: t("contact.noCompany") },
          ...companyOptions.map((c) => ({ id: c.id, label: c.name })),
        ])}
        {select(
          "lifecycle_stage",
          t("contact.field.stage"),
          STAGES.map((stage: Stage) => ({ id: stage, label: stageLabel(t, stage) })),
        )}
        {select("owner_user_id", t("records.field.owner"), [
          { id: "", label: t("records.owner.none") },
          ...owners,
        ])}
        {select(
          "source",
          t("contact.field.source"),
          (contact && !USER_SOURCES.includes(contact.source as (typeof USER_SOURCES)[number])
            ? [contact.source, ...USER_SOURCES]
            : [...USER_SOURCES]
          ).map((source) => ({ id: source, label: sourceLabel(t, source) })),
        )}
        <p className="form-hint wide">{t("contact.hint")}</p>
        {refusal && !(refusal instanceof FieldErrors && refusal.fields.length > 0) ? (
          <div className="notice error wide" role="alert">
            <p>{t(refusalMessage(refusal))}</p>
            {duplicateOf ? (
              <Button size="sm" onPress={() => { onOpenExisting(duplicateOf); }}>
                {t("records.openExisting")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
