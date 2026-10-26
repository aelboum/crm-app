import { Archive, ArchiveRestore, Pencil, Plus } from "lucide-react";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { ApiError } from "../api/client";
import {
  activeFields,
  FIELD_TYPES,
  type FieldDefinition,
  type FieldEntity,
  type FieldType,
  useArchiveField,
  useCreateField,
  useFieldDefinitions,
  useUpdateField,
} from "../api/customFields";
import { FieldErrors } from "../api/records";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { TYPE_LABEL } from "../records/CustomFields";

/*
 * Settings › Custom fields (ScreenSettings.dc.html "Extra fields on contact
 * records"; decision P3-D). One list per entity. Everyone sees the fields;
 * Owners and Admins (`update_workspace`) add them, rename them, change a
 * select's options, and archive or restore them; the server enforces that.
 * A field's key and type are fixed once it exists, as its values depend on
 * them. Archiving hides a field and keeps its values.
 */

const ENTITY_LABEL: Record<FieldEntity, MessageId> = {
  contact: "fields.entity.contact",
  company: "fields.entity.company",
};

/** A key suggested from a label: "Insurance carrier" → "insurance_carrier". */
function suggestKey(label: string): string {
  const key = label
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 40);
  return key;
}

const optionList = (raw: string) =>
  raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

function failure(error: unknown): MessageId {
  if (error instanceof FieldErrors) return "fields.error.invalid";
  if (error instanceof ApiError) {
    switch (error.code) {
      case "duplicate_custom_field_key":
        return "fields.error.duplicateKey";
      case "custom_field_limit_reached":
        return "fields.error.limit";
      case "invalid_options":
        return "fields.error.options";
      case "stale_version":
        return "fields.error.stale";
      case "custom_field_not_found":
        return "fields.error.gone";
      default:
        if (error.status === 403) return "fields.error.forbidden";
        if (error.status === 422) return "fields.error.invalid";
    }
  }
  return "fields.error.failed";
}

export function FieldSettings({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const t = useT();
  const definitions = useFieldDefinitions(workspaceId);
  const [entity, setEntity] = useState<FieldEntity>("contact");
  const [error, setError] = useState<MessageId | null>(null);

  if (definitions.isPending) return <Loading />;
  if (definitions.isError) {
    return <LoadError error={definitions.error} onRetry={() => void definitions.refetch()} />;
  }
  const { items, max_active: max } = definitions.data;
  const fields = items.filter((field) => field.entity === entity);
  const active = activeFields(items, entity).length;

  return (
    <section className="business-card field-settings" aria-label={t("settings.fields")}>
      <div className="chip-group field-entities" role="group" aria-label={t("fields.entities")}>
        {(["contact", "company"] as const).map((option) => (
          <AriaButton
            key={option}
            className={entity === option ? "chip active" : "chip"}
            aria-pressed={entity === option}
            onPress={() => {
              setEntity(option);
              setError(null);
            }}
          >
            {t(ENTITY_LABEL[option])}
          </AriaButton>
        ))}
      </div>
      <p className="profile-note">{t("fields.count", { count: active, max })}</p>
      {canEdit ? null : <p className="profile-note">{t("fields.readOnly")}</p>}
      {error ? (
        <p className="notice error" role="alert">
          {t(error)}
        </p>
      ) : null}
      {canEdit ? (
        <NewField
          key={entity}
          workspaceId={workspaceId}
          entity={entity}
          position={fields.length}
          full={active >= max}
          onError={setError}
        />
      ) : null}
      {fields.length === 0 ? (
        <p className="muted">{t("fields.empty")}</p>
      ) : (
        <ul className="field-rows" aria-label={t(ENTITY_LABEL[entity])}>
          {fields.map((field) => (
            <FieldRowItem
              key={field.id}
              workspaceId={workspaceId}
              field={field}
              canEdit={canEdit}
              full={active >= max}
              onError={setError}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function NewField({
  workspaceId,
  entity,
  position,
  full,
  onError,
}: {
  workspaceId: string;
  entity: FieldEntity;
  /** New fields go last. */
  position: number;
  full: boolean;
  onError: (error: MessageId | null) => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateField(workspaceId);
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [keyTouched, setKeyTouched] = useState(false);
  const [type, setType] = useState<FieldType>("text");
  const [options, setOptions] = useState("");

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    onError(null);
    create.mutate(
      {
        entity,
        key: key.trim(),
        label: label.trim(),
        field_type: type,
        position,
        ...(type === "select" ? { options: optionList(options) } : {}),
      },
      {
        onSuccess: (field) => {
          toast(t("fields.created", { label: field.label }));
          setLabel("");
          setKey("");
          setKeyTouched(false);
          setOptions("");
        },
        onError: (problem) => {
          onError(failure(problem));
        },
      },
    );
  };

  return (
    <form className="field-new" onSubmit={submit} aria-label={t("fields.new")}>
      <div className="form-field">
        <label className="form-label" htmlFor="field-new-label">
          {t("fields.label")}
        </label>
        <input
          id="field-new-label"
          className="form-input"
          value={label}
          maxLength={60}
          onChange={(event) => {
            setLabel(event.target.value);
            if (!keyTouched) setKey(suggestKey(event.target.value));
          }}
        />
      </div>
      <div className="form-field">
        <label className="form-label" htmlFor="field-new-key">
          {t("fields.key")}
        </label>
        <input
          id="field-new-key"
          className="form-input"
          value={key}
          maxLength={40}
          aria-describedby="field-new-key-hint"
          onChange={(event) => {
            setKey(event.target.value);
            setKeyTouched(true);
          }}
        />
        <span id="field-new-key-hint" className="form-hint">
          {t("fields.keyHint")}
        </span>
      </div>
      <div className="form-field">
        <label className="form-label" htmlFor="field-new-type">
          {t("fields.type")}
        </label>
        <select
          id="field-new-type"
          className="form-input form-select"
          value={type}
          onChange={(event) => {
            setType(event.target.value as FieldType);
          }}
        >
          {FIELD_TYPES.map((option) => (
            <option key={option} value={option}>
              {t(TYPE_LABEL[option])}
            </option>
          ))}
        </select>
      </div>
      {type === "select" ? (
        <div className="form-field wide">
          <label className="form-label" htmlFor="field-new-options">
            {t("fields.options")}
          </label>
          <textarea
            id="field-new-options"
            className="form-input"
            rows={3}
            value={options}
            aria-describedby="field-new-options-hint"
            onChange={(event) => {
              setOptions(event.target.value);
            }}
          />
          <span id="field-new-options-hint" className="form-hint">
            {t("fields.optionsHint")}
          </span>
        </div>
      ) : null}
      <div className="field-new-actions wide">
        <Button type="submit" isDisabled={!label.trim() || !key.trim() || create.isPending || full}>
          <Plus size={14} aria-hidden="true" />
          {t("fields.add")}
        </Button>
      </div>
    </form>
  );
}

function FieldRowItem({
  workspaceId,
  field,
  canEdit,
  full,
  onError,
}: {
  workspaceId: string;
  field: FieldDefinition;
  canEdit: boolean;
  full: boolean;
  onError: (error: MessageId | null) => void;
}) {
  const t = useT();
  const toast = useToast();
  const archive = useArchiveField(workspaceId);
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <EditField
        workspaceId={workspaceId}
        field={field}
        onDone={() => {
          setEditing(false);
        }}
        onError={onError}
      />
    );
  }
  const toggle = () => {
    onError(null);
    archive.mutate(
      { id: field.id, archived: !field.archived },
      {
        onSuccess: () => {
          toast(field.archived ? t("fields.restored") : t("fields.archived"));
        },
        onError: (problem) => {
          onError(failure(problem));
        },
      },
    );
  };
  return (
    <li className={field.archived ? "field-row-item archived" : "field-row-item"}>
      <div className="field-row-text">
        <span className="field-row-label">{field.label}</span>
        <span className="field-row-meta">
          {field.key} · {t(TYPE_LABEL[field.field_type])}
          {field.options?.length ? ` · ${field.options.join(", ")}` : ""}
          {field.archived ? ` · ${t("fields.archivedBadge")}` : ""}
        </span>
      </div>
      {canEdit ? (
        <span className="tag-row-actions">
          {field.archived ? null : (
            <Button
              size="sm"
              variant="ghost"
              aria-label={t("fields.edit", { label: field.label })}
              onPress={() => {
                onError(null);
                setEditing(true);
              }}
            >
              <Pencil size={13} aria-hidden="true" />
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            aria-label={t(field.archived ? "fields.restore" : "fields.archive", { label: field.label })}
            isDisabled={archive.isPending || (field.archived && full)}
            onPress={toggle}
          >
            {field.archived ? <ArchiveRestore size={13} aria-hidden="true" /> : <Archive size={13} aria-hidden="true" />}
          </Button>
        </span>
      ) : null}
    </li>
  );
}

function EditField({
  workspaceId,
  field,
  onDone,
  onError,
}: {
  workspaceId: string;
  field: FieldDefinition;
  onDone: () => void;
  onError: (error: MessageId | null) => void;
}) {
  const t = useT();
  const toast = useToast();
  const update = useUpdateField(workspaceId);
  const [label, setLabel] = useState(field.label);
  const [options, setOptions] = useState((field.options ?? []).join("\n"));
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
  }, []);
  const labelId = `field-edit-${field.id}-label`;
  const optionsId = `field-edit-${field.id}-options`;

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const changes: { label?: string; options?: string[] } = {};
    if (label.trim() !== field.label) changes.label = label.trim();
    const nextOptions = optionList(options);
    if (field.field_type === "select" && nextOptions.join("\n") !== (field.options ?? []).join("\n")) {
      changes.options = nextOptions;
    }
    if (Object.keys(changes).length === 0) {
      onDone();
      return;
    }
    onError(null);
    update.mutate(
      { id: field.id, version: field.version, changes },
      {
        onSuccess: () => {
          toast(t("fields.saved"));
          onDone();
        },
        onError: (problem) => {
          onError(failure(problem));
        },
      },
    );
  };

  return (
    <li className="field-row-item editing">
      <form className="field-new" onSubmit={submit} aria-label={t("fields.edit", { label: field.label })}>
        <div className="form-field">
          <label className="form-label" htmlFor={labelId}>
            {t("fields.label")}
          </label>
          <input
            ref={input}
            id={labelId}
            className="form-input"
            value={label}
            maxLength={60}
            onChange={(event) => {
              setLabel(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") onDone();
            }}
          />
        </div>
        {field.field_type === "select" ? (
          <div className="form-field wide">
            <label className="form-label" htmlFor={optionsId}>
              {t("fields.options")}
            </label>
            <textarea
              id={optionsId}
              className="form-input"
              rows={3}
              value={options}
              onChange={(event) => {
                setOptions(event.target.value);
              }}
            />
          </div>
        ) : null}
        <div className="field-new-actions wide">
          <Button type="submit" variant="primary" isDisabled={update.isPending}>
            {t("fields.save")}
          </Button>
          <Button onPress={onDone}>{t("confirm.cancel")}</Button>
        </div>
      </form>
    </li>
  );
}
