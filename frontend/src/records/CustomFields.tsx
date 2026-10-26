import { Link } from "@tanstack/react-router";
import { useIntl } from "react-intl";

import type { FieldDefinition } from "../api/customFields";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { FieldRow } from "./parts";

/*
 * Custom field values on a contact or company (decision P3-D). The drawer
 * shows the active fields as the design's "Custom fields" card with
 * "Manage" (ScreenContacts.dc.html); the create and edit dialogs get one
 * input per active field, typed by the field. Inputs hold text; values are
 * parsed when sent, and only the keys that changed are sent.
 */

type Stored = Record<string, unknown>;
type Value = string | number | boolean | null;
/** Values as the API takes them, by key. */
export type CustomValues = Record<string, Value>;
/** What the inputs hold, by key. A yes/no field holds "true", "false" or "". */
export type CustomDraft = Record<string, string>;

export const TYPE_LABEL: Record<FieldDefinition["field_type"], MessageId> = {
  text: "fields.type.text",
  number: "fields.type.number",
  date: "fields.type.date",
  boolean: "fields.type.boolean",
  select: "fields.type.select",
};

/** A stored value as text: scalars as written, anything else as JSON. */
function asText(value: unknown): string {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : JSON.stringify(value);
}

export function draftOf(fields: FieldDefinition[], stored: Stored | undefined): CustomDraft {
  const draft: CustomDraft = {};
  for (const field of fields) {
    const value = stored?.[field.key];
    draft[field.key] =
      value === undefined || value === null ? "" : asText(value);
  }
  return draft;
}

/** The input's value as the API takes it; `undefined` for a number that is not one. */
function parse(field: FieldDefinition, raw: string): Value | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  switch (field.field_type) {
    case "number": {
      const number = Number(trimmed);
      return Number.isFinite(number) ? number : undefined;
    }
    case "boolean":
      return trimmed === "true";
    default:
      return trimmed;
  }
}

/** Keys whose input holds no valid value (a number that is not one). */
export function draftProblems(fields: FieldDefinition[], draft: CustomDraft): string[] {
  return fields.filter((field) => parse(field, draft[field.key] ?? "") === undefined).map((field) => field.key);
}

/** The values to create a record with: every filled field. */
export function createValues(fields: FieldDefinition[], draft: CustomDraft): CustomValues {
  const values: CustomValues = {};
  for (const field of fields) {
    const value = parse(field, draft[field.key] ?? "");
    if (value !== null && value !== undefined) values[field.key] = value;
  }
  return values;
}

/** Only the keys that changed; `null` clears one. */
export function changedValues(
  fields: FieldDefinition[],
  draft: CustomDraft,
  stored: Stored | undefined,
): CustomValues {
  const changes: CustomValues = {};
  for (const field of fields) {
    const value = parse(field, draft[field.key] ?? "");
    const before = stored?.[field.key] ?? null;
    if (value !== undefined && value !== before) changes[field.key] = value;
  }
  return changes;
}

/** One input per active field, for a record dialog's two-column form. */
export function CustomFieldInputs({
  fields,
  draft,
  onChange,
  invalid,
  idPrefix,
}: {
  fields: FieldDefinition[];
  draft: CustomDraft;
  onChange: (key: string, value: string) => void;
  invalid: Set<string>;
  idPrefix: string;
}) {
  const t = useT();
  return (
    <>
      {fields.map((field) => {
        const id = `${idPrefix}-cf-${field.key}`;
        const errorId = `${id}-error`;
        const bad = invalid.has(field.key);
        const value = draft[field.key] ?? "";
        const common = {
          id,
          value,
          className: bad ? "form-input invalid" : "form-input",
          "aria-invalid": bad || undefined,
          "aria-describedby": bad ? errorId : undefined,
          onChange: (event: { target: { value: string } }) => {
            onChange(field.key, event.target.value);
          },
        };
        const choices = field.field_type === "select" ? (field.options ?? []) : [];
        return (
          <div key={field.key} className={field.field_type === "text" ? "form-field wide" : "form-field"}>
            <label className="form-label" htmlFor={id}>
              {field.label}
            </label>
            {field.field_type === "text" ? <input {...common} maxLength={500} /> : null}
            {field.field_type === "number" ? <input {...common} type="number" step="any" inputMode="decimal" /> : null}
            {field.field_type === "date" ? <input {...common} type="date" /> : null}
            {field.field_type === "boolean" ? (
              <select {...common} className={`${common.className} form-select`}>
                <option value="">{t("fields.value.unset")}</option>
                <option value="true">{t("fields.value.yes")}</option>
                <option value="false">{t("fields.value.no")}</option>
              </select>
            ) : null}
            {field.field_type === "select" ? (
              <select {...common} className={`${common.className} form-select`}>
                <option value="">{t("fields.value.unset")}</option>
                {/* A stored value whose option was since removed stays choosable. */}
                {value && !choices.includes(value) ? <option value={value}>{value}</option> : null}
                {choices.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            ) : null}
            {bad ? (
              <span id={errorId} className="form-error">
                {t("fields.error.value")}
              </span>
            ) : null}
          </div>
        );
      })}
    </>
  );
}

function useDisplay() {
  const t = useT();
  const intl = useIntl();
  return (field: FieldDefinition, value: unknown): string => {
    if (value === undefined || value === null) return "—";
    switch (field.field_type) {
      case "boolean":
        return value === true ? t("fields.value.yes") : t("fields.value.no");
      case "number":
        return typeof value === "number" ? intl.formatNumber(value) : asText(value);
      case "date": {
        const date = typeof value === "string" ? new Date(`${value}T00:00:00Z`) : null;
        return date && !Number.isNaN(date.getTime())
          ? intl.formatDate(date, { dateStyle: "medium", timeZone: "UTC" })
          : asText(value);
      }
      default:
        return asText(value);
    }
  };
}

/** The drawer's "Custom fields" card; nothing when the entity has no active fields. */
export function CustomFieldsSection({
  workspaceId,
  fields,
  values,
  canManage,
}: {
  workspaceId: string;
  fields: FieldDefinition[];
  values: Stored;
  /** Whether to link to Settings › Custom fields (Owners and Admins). */
  canManage: boolean;
}) {
  const t = useT();
  const display = useDisplay();
  if (fields.length === 0) return null;
  return (
    <section className="drawer-section" aria-labelledby="custom-fields-title">
      <div className="drawer-section-head">
        <h2 id="custom-fields-title" className="drawer-section-title">
          {t("fields.title")}
        </h2>
        {canManage ? (
          <Link
            className="text-button"
            to="/w/$workspaceId/$section"
            params={{ workspaceId, section: "settings" }}
            search={{ section: "fields" }}
          >
            {t("fields.manage")}
          </Link>
        ) : null}
      </div>
      <dl className="field-list">
        {fields.map((field) => (
          <FieldRow key={field.key} label={field.label}>
            {display(field, values[field.key])}
          </FieldRow>
        ))}
      </dl>
    </section>
  );
}
