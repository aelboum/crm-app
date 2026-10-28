import type { Answer, FieldType, Target } from "../api/forms";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Pieces shared by the form editor's preview and the hosted form page
 * (decision P7-A): one field renderer, so what an Owner previews is what a
 * visitor gets, and the labels of field types, targets and refusals.
 */

export const TYPE_LABEL: Record<FieldType, MessageId> = {
  text: "forms.type.text",
  email: "forms.type.email",
  phone: "forms.type.phone",
  textarea: "forms.type.textarea",
  select: "forms.type.select",
  date: "forms.type.date",
  checkbox: "forms.type.checkbox",
};

export const TARGET_LABEL: Record<Target, MessageId> = {
  first_name: "forms.target.first_name",
  last_name: "forms.target.last_name",
  email: "forms.target.email",
  phone: "forms.target.phone",
  job_title: "forms.target.job_title",
  city: "forms.target.city",
};

/** What the visitor sees for a refused answer, by the server's rule code. */
export function answerError(code: string): MessageId {
  if (code === "required") return "publicForm.error.required";
  if (code === "email_or_phone_required") return "publicForm.error.emailOrPhone";
  return "publicForm.error.invalid";
}

export interface ShownField {
  key: string;
  type: FieldType;
  label: string;
  required: boolean;
  options?: string[] | null;
}

/** One field as a visitor fills it in; `idPrefix` keeps ids unique on a page. */
export function FieldInput({
  field,
  value,
  error,
  idPrefix,
  disabled = false,
  onChange,
}: {
  field: ShownField;
  value: Answer;
  error?: MessageId | null;
  idPrefix: string;
  disabled?: boolean;
  onChange: (value: Answer) => void;
}) {
  const t = useT();
  const id = `${idPrefix}-${field.key}`;
  const errorId = `${id}-error`;
  const described = error ? { "aria-describedby": errorId, "aria-invalid": true } : {};
  const text = typeof value === "string" ? value : "";
  const mark = field.required ? (
    <span className="required" aria-hidden="true">
      {" *"}
    </span>
  ) : null;
  const message = error ? (
    <span id={errorId} className="form-error">
      {t(error)}
    </span>
  ) : null;

  if (field.type === "checkbox") {
    return (
      <div className="form-field public-check">
        <label className="public-check-label" htmlFor={id}>
          <input
            id={id}
            type="checkbox"
            checked={value === true}
            disabled={disabled}
            required={field.required}
            onChange={(event) => {
              onChange(event.target.checked);
            }}
            {...described}
          />
          <span>
            {field.label}
            {mark}
          </span>
        </label>
        {message}
      </div>
    );
  }
  const common = {
    id,
    disabled,
    required: field.required,
    value: text,
    ...described,
  };
  return (
    <div className="form-field">
      <label className="form-label" htmlFor={id}>
        {field.label}
        {mark}
      </label>
      {field.type === "textarea" ? (
        <textarea
          {...common}
          className="form-input public-textarea"
          rows={4}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      ) : field.type === "select" ? (
        <select
          {...common}
          className="form-input form-select"
          onChange={(event) => {
            onChange(event.target.value || null);
          }}
        >
          <option value="">{t("publicForm.choose")}</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <input
          {...common}
          className={error ? "form-input invalid" : "form-input"}
          type={
            field.type === "email" ? "email" : field.type === "phone" ? "tel" : field.type === "date" ? "date" : "text"
          }
          autoComplete={field.type === "email" ? "email" : field.type === "phone" ? "tel" : "off"}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
      {message}
    </div>
  );
}
