import { CircleCheckBig } from "lucide-react";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { type Answer, AnswersRefused, usePublicForm, useSubmitPublicForm } from "../api/forms";
import { newIdempotencyKey } from "../api/records";
import { Loading } from "../components/StateNotice";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { answerError, FieldInput } from "../records/formParts";

/*
 * The hosted form page (decision P7-A 5, 10): /app/f/<workspace>/<key>. No
 * app frame, no sign-in, nothing about the workspace. The visitor's
 * answers go to the public route with one Idempotency-Key per attempt, so
 * a double click or a retry is stored once. The hidden "website" field is
 * the honeypot: people never see or fill it. Refusals come back per field
 * key and are shown next to the field; nothing is checked only here.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.status === 404) return "publicForm.error.gone";
    if (error.status === 429) return "publicForm.error.busy";
    if (error.status === 503) return "publicForm.error.unavailable";
  }
  return "publicForm.error.failed";
}

export function PublicFormPage({ workspaceId, formKey }: { workspaceId: string; formKey: string }) {
  const t = useT();
  const form = usePublicForm(workspaceId, formKey);
  const submit = useSubmitPublicForm(workspaceId, formKey);
  const [values, setValues] = useState<Record<string, Answer>>({});
  const [consent, setConsent] = useState(false);
  const [website, setWebsite] = useState("");
  const [attempt] = useState(newIdempotencyKey);
  // Fields changed since the last refusal no longer show its message.
  const [edited, setEdited] = useState<ReadonlySet<string>>(new Set());
  const thanks = useRef<HTMLDivElement>(null);
  const refused = submit.error instanceof AnswersRefused ? submit.error.fields : {};

  useEffect(() => {
    if (submit.isSuccess) thanks.current?.focus();
  }, [submit.isSuccess]);

  let body;
  if (form.isPending) {
    body = <Loading />;
  } else if (form.isError) {
    body = (
      <p className="notice error" role="alert">
        {t(failure(form.error))}
      </p>
    );
  } else if (submit.isSuccess) {
    body = (
      <div className="public-thanks" ref={thanks} tabIndex={-1} role="status">
        <CircleCheckBig size={28} aria-hidden="true" />
        <p>{submit.data.thank_you}</p>
      </div>
    );
  } else {
    const onSubmit = (event: SyntheticEvent) => {
      event.preventDefault();
      setEdited(new Set());
      submit.mutate({ answers: values, consent, website, attempt });
    };
    body = (
      <form className="public-form" noValidate onSubmit={onSubmit} aria-labelledby="public-form-title">
        <h1 id="public-form-title" className="public-form-title">
          {form.data.name}
        </h1>
        <p className="form-hint">{t("publicForm.requiredHint")}</p>
        {form.data.fields.map((field) => {
          const code = edited.has(field.key) ? undefined : refused[field.key];
          return (
            <FieldInput
              key={field.key}
              field={field}
              idPrefix="public"
              value={values[field.key] ?? null}
              error={code ? answerError(code) : null}
              onChange={(value) => {
                setValues((current) => ({ ...current, [field.key]: value }));
                setEdited((current) => new Set(current).add(field.key));
              }}
            />
          );
        })}
        {form.data.consent_text ? (
          <label className="public-check-label public-consent" htmlFor="public-consent">
            <input
              id="public-consent"
              type="checkbox"
              checked={consent}
              onChange={(event) => {
                setConsent(event.target.checked);
              }}
            />
            <span className="public-consent-text">{form.data.consent_text}</span>
          </label>
        ) : null}
        <div className="public-honeypot" aria-hidden="true">
          <label htmlFor="public-website">{t("publicForm.honeypot")}</label>
          <input
            id="public-website"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => {
              setWebsite(event.target.value);
            }}
          />
        </div>
        {submit.isError ? (
          <p className="notice error" role="alert">
            {submit.error instanceof AnswersRefused ? t("publicForm.error.check") : t(failure(submit.error))}
          </p>
        ) : null}
        <button type="submit" className="btn btn-primary btn-lg public-submit" disabled={submit.isPending}>
          {submit.isPending ? t("publicForm.sending") : t("publicForm.submit")}
        </button>
      </form>
    );
  }
  return (
    <main id="main" className="public-form-page">
      <div className="public-form-card">{body}</div>
      <p className="public-form-foot">{t("publicForm.footer")}</p>
    </main>
  );
}
