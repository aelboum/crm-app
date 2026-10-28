import { ArrowDown, ArrowLeft, ArrowUp, FileText, Link2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { ApiError } from "../api/client";
import {
  type Answer,
  FIELD_TYPES,
  type FieldType,
  type Form,
  type FormField,
  FormRefusal,
  MAX_FIELDS,
  newFieldKey,
  publicPath,
  starterFields,
  type Target,
  TARGETS,
  useCreateForm,
  useDeleteForm,
  useForm,
  useForms,
  useSubmissions,
  useUpdateForm,
} from "../api/forms";
import { useAccess, useMe, useMembers } from "../api/queries";
import { newIdempotencyKey } from "../api/records";
import { useTags } from "../api/tags";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { FieldInput, TARGET_LABEL, TYPE_LABEL } from "./formParts";
import { ownerOptions, When } from "./parts";

/*
 * Forms (ScreenForms.dc.html, decision P7-A). The list shows each form's
 * status, fields and submissions; the editor has the design's three
 * columns: the fields (move up, move down, remove, and an "Add" palette),
 * a live preview built from the same renderer as the hosted page, and
 * "After someone submits" (tag, contact owner, thank-you message, consent
 * wording). Publishing saves and publishes in one change. Below the editor
 * are the submissions. Landing pages, views and conversion, the embed
 * script and "Start automation" are not built (P7-A 1). Owners and Admins
 * (`manage_forms`) change forms; everyone else sees them read-only.
 */

const FIELD_ERRORS: Record<string, MessageId> = {
  field_key: "forms.error.field",
  duplicate_field_key: "forms.error.field",
  field_type: "forms.error.field",
  field_label: "forms.error.fieldLabel",
  field_options: "forms.error.fieldOptions",
  field_target: "forms.error.fieldTarget",
  duplicate_field_target: "forms.error.duplicateTarget",
};

const CODES: Record<string, MessageId> = {
  invalid_name: "forms.error.name",
  invalid_thank_you: "forms.error.thankYou",
  invalid_consent_text: "forms.error.consentText",
  first_name_field_required: "forms.error.firstName",
  email_or_phone_field_required: "forms.error.emailOrPhone",
  consent_needs_email_field: "forms.error.consentEmail",
  tag_not_found: "forms.error.tag",
  contact_owner_not_member: "forms.error.owner",
  stale_version: "forms.error.stale",
  form_limit: "forms.error.limit",
  form_not_found: "forms.error.gone",
  field_count: "forms.error.fieldCount",
};

function failure(error: unknown): { id: MessageId; field?: number } {
  if (error instanceof FormRefusal && error.code) {
    const fieldMessage = FIELD_ERRORS[error.code];
    if (fieldMessage && error.field !== undefined && error.field >= 0) return { id: fieldMessage, field: error.field };
    const message = CODES[error.code];
    if (message) return { id: message };
  }
  if (error instanceof ApiError) {
    if (error.status === 403) return { id: "forms.error.forbidden" };
    if (error.status === 404) return { id: "forms.error.gone" };
  }
  return { id: "forms.error.failed" };
}

export function FormsPage({
  workspaceId,
  formId,
  onOpen,
  onOpenContact,
}: {
  workspaceId: string;
  formId: string | undefined;
  onOpen: (id: string | undefined) => void;
  onOpenContact: (id: string) => void;
}) {
  const access = useAccess(workspaceId);
  const canManage = access.data?.actions.manage_forms === true;
  if (formId) {
    return (
      <FormEditorLoader
        workspaceId={workspaceId}
        formId={formId}
        canManage={canManage}
        onBack={() => {
          onOpen(undefined);
        }}
        onOpenContact={onOpenContact}
      />
    );
  }
  return <FormList workspaceId={workspaceId} canManage={canManage} onOpen={onOpen} />;
}

function FormList({
  workspaceId,
  canManage,
  onOpen,
}: {
  workspaceId: string;
  canManage: boolean;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const forms = useForms(workspaceId);
  const create = useCreateForm(workspaceId);
  const [key, setKey] = useState(newIdempotencyKey);
  const [error, setError] = useState<MessageId | null>(null);

  const createForm = () => {
    setError(null);
    create.mutate(
      {
        key,
        body: {
          name: t("forms.untitled"),
          fields: starterFields({
            first: t("forms.target.first_name"),
            email: t("forms.target.email"),
            phone: t("forms.target.phone"),
          }),
        },
      },
      {
        onSuccess: (form) => {
          setKey(newIdempotencyKey());
          onOpen(form.id);
        },
        onError: (failed) => {
          setError(failure(failed).id);
        },
      },
    );
  };

  return (
    <div className="records-page forms-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.marketing")}</p>
          <h1 className="records-title">{t("forms.title")}</h1>
        </div>
        {canManage ? (
          <div className="records-actions">
            <Button variant="primary" onPress={createForm} isDisabled={create.isPending}>
              <Plus size={15} aria-hidden="true" />
              {t("forms.new")}
            </Button>
          </div>
        ) : null}
      </div>
      <p className="forms-scope muted">{t("forms.scope")}</p>
      {error ? (
        <p className="notice error" role="alert">
          {t(error)}
        </p>
      ) : null}
      {forms.isPending ? (
        <div className="records-card">
          <Loading />
        </div>
      ) : forms.isError ? (
        <div className="records-card">
          <LoadError error={forms.error} onRetry={() => void forms.refetch()} />
        </div>
      ) : forms.data.items.length === 0 ? (
        <div className="records-card tasks-empty">
          <FileText size={28} aria-hidden="true" />
          <p className="tasks-empty-title">{t("forms.empty.title")}</p>
          <p className="muted">{canManage ? t("forms.empty.body") : t("forms.empty.reader")}</p>
        </div>
      ) : (
        <ul className="form-cards">
          {forms.data.items.map((form) => (
            <li key={form.id}>
              <AriaButton
                className="form-card"
                onPress={() => {
                  onOpen(form.id);
                }}
              >
                <span className="form-card-preview" aria-hidden="true">
                  {form.fields.slice(0, 3).map((field) => (
                    <span key={field.key} className="form-card-line" />
                  ))}
                  <span className="form-card-line submit" />
                </span>
                <span className="form-card-body">
                  <span className="form-card-head">
                    <span className="form-card-name">{form.name}</span>
                    <Badge tone={form.status === "published" ? "success" : "neutral"}>
                      {t(form.status === "published" ? "forms.status.published" : "forms.status.draft")}
                    </Badge>
                  </span>
                  <span className="form-card-sub">
                    {t("forms.card.fields", { count: form.fields.length })} · {t("forms.card.updated")}{" "}
                    <When value={form.updated_at} />
                  </span>
                  <span className="form-card-stats">
                    <strong>{form.submission_count}</strong> {t("forms.card.submissions", { count: form.submission_count })}
                  </span>
                </span>
              </AriaButton>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FormEditorLoader({
  workspaceId,
  formId,
  canManage,
  onBack,
  onOpenContact,
}: {
  workspaceId: string;
  formId: string;
  canManage: boolean;
  onBack: () => void;
  onOpenContact: (id: string) => void;
}) {
  const form = useForm(workspaceId, formId);
  if (form.isPending) return <Loading />;
  if (form.isError) {
    return (
      <div className="records-page">
        <LoadError error={form.error} onRetry={() => void form.refetch()} />
      </div>
    );
  }
  return (
    <FormEditor
      key={`${form.data.id}:${String(form.data.version)}`}
      workspaceId={workspaceId}
      form={form.data}
      canManage={canManage}
      onBack={onBack}
      onOpenContact={onOpenContact}
    />
  );
}

interface Draft {
  name: string;
  fields: FormField[];
  tag_id: string;
  contact_owner_user_id: string;
  thank_you: string;
  consent_text: string;
}

function draftOf(form: Form): Draft {
  return {
    name: form.name,
    fields: form.fields.map((field) => ({ ...field })),
    tag_id: form.tag_id ?? "",
    contact_owner_user_id: form.contact_owner_user_id,
    thank_you: form.thank_you,
    consent_text: form.consent_text ?? "",
  };
}

function FormEditor({
  workspaceId,
  form,
  canManage,
  onBack,
  onOpenContact,
}: {
  workspaceId: string;
  form: Form;
  canManage: boolean;
  onBack: () => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const access = useAccess(workspaceId);
  const me = useMe();
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const tags = useTags(workspaceId);
  const update = useUpdateForm(workspaceId);
  const remove = useDeleteForm(workspaceId);
  const [draft, setDraft] = useState<Draft>(() => draftOf(form));
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<{ id: MessageId; field?: number } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const saved = draftOf(form);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const published = form.status === "published";
  const link = `${window.location.origin}${publicPath(workspaceId, form.public_key)}`;
  const owners = ownerOptions(t, members.data?.items ?? [], me.data?.user_id);
  const ownerChoices = owners.some((owner) => owner.id === draft.contact_owner_user_id)
    ? owners
    : [...owners, { id: draft.contact_owner_user_id, label: t("forms.owner.other") }];
  const current = draft.fields[selected];

  const change = (patch: Partial<Draft>) => {
    setDraft((before) => ({ ...before, ...patch }));
  };
  const changeField = (index: number, patch: Partial<FormField>) => {
    change({ fields: draft.fields.map((field, i) => (i === index ? { ...field, ...patch } : field)) });
  };
  const move = (index: number, by: number) => {
    const to = index + by;
    if (to < 0 || to >= draft.fields.length) return;
    const fields = [...draft.fields];
    const [moved] = fields.splice(index, 1);
    if (moved) fields.splice(to, 0, moved);
    change({ fields });
    setSelected(to);
  };
  const removeField = (index: number) => {
    change({ fields: draft.fields.filter((_, i) => i !== index) });
    setSelected(Math.max(0, Math.min(selected, draft.fields.length - 2)));
  };
  const addField = (type: FieldType) => {
    const key = newFieldKey(
      type,
      draft.fields.map((field) => field.key),
    );
    const field: FormField = {
      key,
      type,
      label: t(TYPE_LABEL[type]),
      required: false,
      target: null,
      options: type === "select" ? [t("forms.option.first"), t("forms.option.second")] : null,
    };
    change({ fields: [...draft.fields, field] });
    setSelected(draft.fields.length);
  };

  const changes = () => ({
    ...(draft.name !== saved.name ? { name: draft.name } : {}),
    ...(JSON.stringify(draft.fields) !== JSON.stringify(saved.fields)
      ? {
          // Blank option lines are editing leftovers, not options.
          fields: draft.fields.map((field) =>
            field.options ? { ...field, options: field.options.map((o) => o.trim()).filter(Boolean) } : field,
          ),
        }
      : {}),
    ...(draft.tag_id !== saved.tag_id ? { tag_id: draft.tag_id || null } : {}),
    ...(draft.contact_owner_user_id !== saved.contact_owner_user_id
      ? { contact_owner_user_id: draft.contact_owner_user_id }
      : {}),
    ...(draft.thank_you !== saved.thank_you ? { thank_you: draft.thank_you } : {}),
    ...(draft.consent_text !== saved.consent_text ? { consent_text: draft.consent_text.trim() || null } : {}),
  });

  const save = (status?: "published" | "draft") => {
    setError(null);
    update.mutate(
      { id: form.id, version: form.version, changes: { ...changes(), ...(status ? { status } : {}) } },
      {
        onSuccess: () => {
          toast(
            t(status === "published" ? "forms.published" : status === "draft" ? "forms.unpublished" : "forms.saved"),
          );
        },
        onError: (failed) => {
          const found = failure(failed);
          setError(found);
          if (found.field !== undefined) setSelected(found.field);
        },
      },
    );
  };

  const copyLink = () => {
    void navigator.clipboard.writeText(link).then(
      () => {
        toast(t("forms.copied"));
      },
      () => {
        setError({ id: "forms.error.copy" });
      },
    );
  };

  return (
    <div className="form-editor">
      <div className="form-editor-bar">
        <Button size="sm" onPress={onBack} aria-label={t("forms.back")}>
          <ArrowLeft size={15} aria-hidden="true" />
        </Button>
        <div className="form-editor-name">
          <span className="records-kicker">{t("forms.title")}</span>
          {canManage ? (
            <>
              <label className="sr-only" htmlFor="form-name">
                {t("forms.field.name")}
              </label>
              <input
                id="form-name"
                className="form-name-input"
                value={draft.name}
                maxLength={120}
                onChange={(event) => {
                  change({ name: event.target.value });
                }}
              />
            </>
          ) : (
            <h1 className="form-name-text">{form.name}</h1>
          )}
        </div>
        <Badge tone={published ? "success" : "neutral"}>
          {t(published ? "forms.status.published" : "forms.status.draft")}
        </Badge>
        {published ? (
          <>
            <a className="form-link mono" href={link} target="_blank" rel="noreferrer">
              {publicPath(workspaceId, form.public_key)}
            </a>
            <Button size="sm" onPress={copyLink}>
              <Link2 size={14} aria-hidden="true" />
              {t("forms.copy")}
            </Button>
          </>
        ) : null}
        {canManage ? (
          <span className="form-editor-actions">
            <Button
              size="sm"
              onPress={() => {
                save();
              }}
              isDisabled={!dirty || update.isPending}
            >
              {t("forms.save")}
            </Button>
            <Button
              size="sm"
              variant={published ? "secondary" : "primary"}
              onPress={() => {
                save(published ? "draft" : "published");
              }}
              isDisabled={update.isPending}
            >
              {t(published ? "forms.unpublish" : dirty ? "forms.saveAndPublish" : "forms.publish")}
            </Button>
          </span>
        ) : null}
      </div>
      {error ? (
        <p className="notice error form-editor-notice" role="alert">
          {error.field !== undefined
            ? t(error.id, { position: error.field + 1 })
            : t(error.id)}
        </p>
      ) : null}
      {dirty ? <p className="form-editor-dirty">{t("forms.unsaved")}</p> : null}

      <div className="form-editor-columns">
        <section className="form-panel form-fields-panel" aria-labelledby="form-fields-title">
          <h2 id="form-fields-title" className="form-panel-title">
            {t("forms.fields")}
          </h2>
          <ol className="form-field-list">
            {draft.fields.map((field, index) => (
              <li key={field.key} className={index === selected ? "form-field-item selected" : "form-field-item"}>
                <AriaButton
                  className="form-field-pick"
                  aria-pressed={index === selected}
                  onPress={() => {
                    setSelected(index);
                  }}
                >
                  <span className="form-field-name">{field.label}</span>
                  <span className="form-field-type">{t(TYPE_LABEL[field.type])}</span>
                </AriaButton>
                {canManage ? (
                  <span className="form-field-tools">
                    <AriaButton
                      className="icon-button"
                      aria-label={t("forms.moveUp", { label: field.label })}
                      isDisabled={index === 0}
                      onPress={() => {
                        move(index, -1);
                      }}
                    >
                      <ArrowUp size={13} aria-hidden="true" />
                    </AriaButton>
                    <AriaButton
                      className="icon-button"
                      aria-label={t("forms.moveDown", { label: field.label })}
                      isDisabled={index === draft.fields.length - 1}
                      onPress={() => {
                        move(index, 1);
                      }}
                    >
                      <ArrowDown size={13} aria-hidden="true" />
                    </AriaButton>
                    <AriaButton
                      className="icon-button"
                      aria-label={t("forms.removeField", { label: field.label })}
                      isDisabled={draft.fields.length === 1}
                      onPress={() => {
                        removeField(index);
                      }}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </AriaButton>
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
          {current ? (
            <FieldSettings
              field={current}
              disabled={!canManage}
              takenTargets={draft.fields
                .filter((_, i) => i !== selected)
                .flatMap((field) => (field.target ? [field.target] : []))}
              onChange={(patch) => {
                changeField(selected, patch);
              }}
            />
          ) : null}
          {canManage ? (
            <div className="form-palette">
              <h3 className="form-panel-subtitle">{t("forms.add")}</h3>
              <div className="form-palette-buttons">
                {FIELD_TYPES.map((type) => (
                  <Button
                    key={type}
                    size="sm"
                    className="form-palette-button"
                    isDisabled={draft.fields.length >= MAX_FIELDS}
                    onPress={() => {
                      addField(type);
                    }}
                    aria-label={t("forms.addType", { type: t(TYPE_LABEL[type]) })}
                  >
                    <Plus size={12} aria-hidden="true" />
                    {t(TYPE_LABEL[type])}
                  </Button>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        <section className="form-panel form-preview-panel" aria-labelledby="form-preview-title">
          <h2 id="form-preview-title" className="form-panel-title">
            {t("forms.preview")}
          </h2>
          <div className="form-preview" inert>
            <p className="public-form-title">{draft.name}</p>
            {draft.fields.map((field) => (
              <FieldInput
                key={field.key}
                field={field}
                idPrefix="preview"
                value={null as Answer}
                disabled
                onChange={() => undefined}
              />
            ))}
            {draft.consent_text.trim() ? (
              <label className="public-check-label public-consent">
                <input type="checkbox" disabled />
                <span className="public-consent-text">{draft.consent_text}</span>
              </label>
            ) : null}
            <span className="btn btn-primary btn-lg public-submit">{t("publicForm.submit")}</span>
          </div>
        </section>

        <section className="form-panel form-settings-panel" aria-labelledby="form-after-title">
          <h2 id="form-after-title" className="form-panel-title">
            {t("forms.after")}
          </h2>
          <p className="form-after-rule">{t("forms.after.contact")}</p>
          <div className="form-field">
            <label className="form-label" htmlFor="form-tag">
              {t("forms.field.tag")}
            </label>
            <select
              id="form-tag"
              className="form-input form-select"
              value={draft.tag_id}
              disabled={!canManage}
              onChange={(event) => {
                change({ tag_id: event.target.value });
              }}
            >
              <option value="">{t("forms.tag.none")}</option>
              {(tags.data?.items ?? []).map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="form-owner">
              {t("forms.field.owner")}
            </label>
            <select
              id="form-owner"
              className="form-input form-select"
              value={draft.contact_owner_user_id}
              disabled={!canManage}
              onChange={(event) => {
                change({ contact_owner_user_id: event.target.value });
              }}
            >
              {ownerChoices.map((owner) => (
                <option key={owner.id} value={owner.id}>
                  {owner.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="form-thanks">
              {t("forms.field.thankYou")}
            </label>
            <textarea
              id="form-thanks"
              className="form-input form-textarea"
              rows={3}
              maxLength={500}
              value={draft.thank_you}
              disabled={!canManage}
              onChange={(event) => {
                change({ thank_you: event.target.value });
              }}
            />
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="form-consent">
              {t("forms.field.consent")}
            </label>
            <textarea
              id="form-consent"
              className="form-input form-textarea"
              rows={3}
              maxLength={500}
              value={draft.consent_text}
              disabled={!canManage}
              aria-describedby="form-consent-hint"
              onChange={(event) => {
                change({ consent_text: event.target.value });
              }}
            />
            <p id="form-consent-hint" className="form-hint">
              {t("forms.consentHint")}
            </p>
          </div>
          <dl className="form-stats">
            <div>
              <dt>{t("forms.stats.submissions")}</dt>
              <dd>{form.submission_count}</dd>
            </div>
            <div>
              <dt>{t("forms.stats.last")}</dt>
              <dd>{form.last_submission_at ? <When value={form.last_submission_at} /> : "—"}</dd>
            </div>
          </dl>
          {canManage ? (
            <Button
              variant="destructive"
              size="sm"
              onPress={() => {
                setConfirming(true);
              }}
            >
              <Trash2 size={14} aria-hidden="true" />
              {t("forms.delete")}
            </Button>
          ) : null}
        </section>
      </div>

      <Submissions workspaceId={workspaceId} form={form} onOpenContact={onOpenContact} />

      <ConfirmDialog
        isOpen={confirming}
        title={t("forms.deleteTitle")}
        message={t("forms.deleteMessage", { name: form.name })}
        confirmLabel={t("forms.deleteConfirm")}
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
          setConfirming(false);
          remove.mutate(
            { id: form.id },
            {
              onSuccess: () => {
                toast(t("forms.deleted"));
                onBack();
              },
              onError: (failed) => {
                setError(failure(failed));
              },
            },
          );
        }}
      />
    </div>
  );
}

function FieldSettings({
  field,
  disabled,
  takenTargets,
  onChange,
}: {
  field: FormField;
  disabled: boolean;
  takenTargets: readonly Target[];
  onChange: (patch: Partial<FormField>) => void;
}) {
  const t = useT();
  const targets = TARGETS[field.type].filter((target) => target === field.target || !takenTargets.includes(target));
  return (
    <div className="form-field-settings" aria-label={t("forms.fieldSettings", { label: field.label })} role="group">
      <div className="form-field">
        <label className="form-label" htmlFor="field-label">
          {t("forms.field.label")}
        </label>
        <input
          id="field-label"
          className="form-input"
          value={field.label}
          maxLength={100}
          disabled={disabled}
          onChange={(event) => {
            onChange({ label: event.target.value });
          }}
        />
      </div>
      <label className="public-check-label" htmlFor="field-required">
        <input
          id="field-required"
          type="checkbox"
          checked={field.required}
          disabled={disabled}
          onChange={(event) => {
            onChange({ required: event.target.checked });
          }}
        />
        <span>{t("forms.field.required")}</span>
      </label>
      {TARGETS[field.type].length ? (
        <div className="form-field">
          <label className="form-label" htmlFor="field-target">
            {t("forms.field.target")}
          </label>
          <select
            id="field-target"
            className="form-input form-select"
            value={field.target ?? ""}
            disabled={disabled}
            onChange={(event) => {
              onChange({ target: (event.target.value || null) as Target | null });
            }}
          >
            <option value="">{t("forms.target.none")}</option>
            {targets.map((target) => (
              <option key={target} value={target}>
                {t(TARGET_LABEL[target])}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {field.type === "select" ? (
        <div className="form-field">
          <label className="form-label" htmlFor="field-options">
            {t("forms.field.options")}
          </label>
          <textarea
            id="field-options"
            className="form-input form-textarea"
            rows={4}
            disabled={disabled}
            value={(field.options ?? []).join("\n")}
            aria-describedby="field-options-hint"
            onChange={(event) => {
              onChange({ options: event.target.value.split("\n") });
            }}
          />
          <p id="field-options-hint" className="form-hint">
            {t("forms.optionsHint")}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Submissions({
  workspaceId,
  form,
  onOpenContact,
}: {
  workspaceId: string;
  form: Form;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const list = useSubmissions(workspaceId, form.id);
  const items = (list.data?.pages ?? []).flatMap((page) => page.items);
  const labels = new Map(form.fields.map((field) => [field.key, field.label]));
  // In the form's field order; answers to fields since removed come last.
  const ordered = (answers: Record<string, string | boolean>) => {
    const keys = [...form.fields.map((field) => field.key), ...Object.keys(answers)];
    return [...new Set(keys)].flatMap((key) => (key in answers ? [[key, answers[key]] as const] : []));
  };
  return (
    <section className="records-card form-submissions" aria-labelledby="form-submissions-title">
      <h2 id="form-submissions-title" className="form-panel-title form-submissions-title">
        {t("forms.submissions")}
        <span className="tab-count">{list.data?.pages[0]?.total ?? ""}</span>
      </h2>
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : items.length === 0 ? (
        <p className="muted form-submissions-empty">{t("forms.submissions.empty")}</p>
      ) : (
        <div className="table-scroll">
          <table className="records-table">
            <thead>
              <tr>
                <th scope="col">{t("forms.submissions.when")}</th>
                <th scope="col">{t("forms.submissions.contact")}</th>
                <th scope="col">{t("forms.submissions.outcome")}</th>
                <th scope="col">{t("forms.submissions.consent")}</th>
                <th scope="col">{t("forms.submissions.answers")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <When value={item.created_at} />
                  </td>
                  <td>
                    {item.contact ? (
                      <AriaButton
                        className="record-link"
                        onPress={() => {
                          if (item.contact) onOpenContact(item.contact.id);
                        }}
                      >
                        {item.contact.name}
                      </AriaButton>
                    ) : (
                      <span className="muted">{t("forms.submissions.noContact")}</span>
                    )}
                  </td>
                  <td>
                    <Badge tone={item.outcome === "created" ? "accent" : "neutral"}>
                      {t(item.outcome === "created" ? "forms.outcome.created" : "forms.outcome.matched")}
                    </Badge>
                  </td>
                  <td>{t(item.consent ? "forms.consent.yes" : "forms.consent.no")}</td>
                  <td className="form-answers">
                    {ordered(item.answers).map(([key, value]) => (
                      <span key={key} className="form-answer">
                        <span className="form-answer-label">{labels.get(key) ?? key}:</span>{" "}
                        {typeof value === "boolean" ? t(value ? "forms.consent.yes" : "forms.consent.no") : value}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {list.hasNextPage ? (
        <div className="records-footer">
          <Button size="sm" onPress={() => void list.fetchNextPage()} isDisabled={list.isFetchingNextPage}>
            {t("records.loadMore")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
