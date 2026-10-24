import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import { useSaveWorkspaceSettings, useWorkspaceSettings, type WorkspaceSettings } from "../api/queries";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import { useT } from "../i18n/useT";

/*
 * Settings › Business profile (ScreenSettings.dc.html L28-40), with the
 * workspace settings that exist (decision P2-F 1): language and region,
 * time zone and default currency. Times are stored in UTC; these only say
 * how to show them. The design's phone, email, website, address and hours
 * have no backend yet and are named as unavailable; the workspace name is
 * shown but cannot be changed (SaaS-OS offers no rename).
 */

const LOCALES = ["en", "en-GB", "en-US", "nl-NL", "de-DE", "fr-FR", "es-ES", "it-IT", "pt-PT", "pl-PL", "sv-SE", "da-DK"];
const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "CAD", "AUD", "JPY"];

/** The options, always including the saved value even when it is not in the short list. */
function withCurrent(options: readonly string[], current: string): string[] {
  return options.includes(current) ? [...options] : [current, ...options];
}

function timeZones(current: string): string[] {
  const known = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return withCurrent(known, current);
}

function label(type: "language" | "currency", code: string): string {
  try {
    const name = new Intl.DisplayNames(["en"], { type }).of(code);
    return name && name !== code ? `${name} (${code})` : code;
  } catch {
    return code;
  }
}

/** How a date and an amount will look with these settings. */
function preview(locale: string, timeZone: string, currency: string): string {
  try {
    const when = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone }).format(
      new Date(),
    );
    const amount = new Intl.NumberFormat(locale, { style: "currency", currency }).format(1234.5);
    return `${when} · ${amount}`;
  } catch {
    return "";
  }
}

type Draft = Pick<WorkspaceSettings, "locale" | "time_zone" | "currency">;

export function BusinessSettings({
  workspaceId,
  workspaceName,
  canEdit,
}: {
  workspaceId: string;
  workspaceName: string;
  canEdit: boolean;
}) {
  const settings = useWorkspaceSettings(workspaceId);
  if (settings.isPending) return <Loading />;
  if (settings.isError) return <LoadError error={settings.error} onRetry={() => void settings.refetch()} />;
  // Keyed by version: after a save or reload the form starts from what is stored.
  return (
    <SettingsForm
      key={settings.data.version}
      workspaceId={workspaceId}
      workspaceName={workspaceName}
      saved={settings.data}
      canEdit={canEdit}
      onReload={() => void settings.refetch()}
    />
  );
}

function SettingsForm({
  workspaceId,
  workspaceName,
  saved,
  canEdit,
  onReload,
}: {
  workspaceId: string;
  workspaceName: string;
  saved: WorkspaceSettings;
  canEdit: boolean;
  onReload: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const save = useSaveWorkspaceSettings(workspaceId);
  const [draft, setDraft] = useState<Draft>({
    locale: saved.locale,
    time_zone: saved.time_zone,
    currency: saved.currency,
  });
  const [error, setError] = useState<"stale" | "invalid" | "denied" | "generic" | null>(null);
  const changes = Object.fromEntries(
    (Object.keys(draft) as (keyof Draft)[])
      .filter((name) => draft[name] !== saved[name])
      .map((name) => [name, draft[name]]),
  );
  const dirty = Object.keys(changes).length > 0;

  function set(name: keyof Draft, value: string) {
    setDraft((current) => ({ ...current, [name]: value }));
    setError(null);
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (!dirty) return;
    save.mutate(
      { version: saved.version, changes },
      {
        onSuccess: () => {
          toast(t("business.saved"));
        },
        onError: (failure) => {
          const status = failure instanceof ApiError ? failure.status : 0;
          const code = failure instanceof ApiError ? failure.code : undefined;
          setError(
            code === "stale_version" ? "stale" : status === 422 ? "invalid" : status === 403 ? "denied" : "generic",
          );
        },
      },
    );
  }

  const message = {
    stale: t("business.error.stale"),
    invalid: t("business.error.invalid"),
    denied: t("business.error.denied"),
    generic: t("records.error.generic"),
  };

  return (
    <form className="business-card" onSubmit={submit} aria-label={t("settings.business")}>
      <div className="business-fields">
        <div className="field-stack">
          <label htmlFor="business-name" className="field-label">
            {t("business.name")}
          </label>
          <input
            id="business-name"
            className="field-input"
            value={workspaceName}
            disabled
            aria-describedby="business-name-note"
          />
          <p id="business-name-note" className="profile-note">
            {t("business.nameNote")}
          </p>
        </div>
        <div className="field-stack">
          <label htmlFor="business-locale" className="field-label">
            {t("business.locale")}
          </label>
          <select
            id="business-locale"
            className="field-input"
            value={draft.locale}
            disabled={!canEdit}
            onChange={(event) => {
              set("locale", event.target.value);
            }}
          >
            {withCurrent(LOCALES, saved.locale).map((code) => (
              <option key={code} value={code}>
                {label("language", code)}
              </option>
            ))}
          </select>
        </div>
        <div className="field-stack">
          <label htmlFor="business-zone" className="field-label">
            {t("business.timeZone")}
          </label>
          <select
            id="business-zone"
            className="field-input"
            value={draft.time_zone}
            disabled={!canEdit}
            onChange={(event) => {
              set("time_zone", event.target.value);
            }}
          >
            {timeZones(saved.time_zone).map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <div className="field-stack">
          <label htmlFor="business-currency" className="field-label">
            {t("business.currency")}
          </label>
          <select
            id="business-currency"
            className="field-input"
            value={draft.currency}
            disabled={!canEdit}
            onChange={(event) => {
              set("currency", event.target.value);
            }}
          >
            {withCurrent(CURRENCIES, saved.currency).map((code) => (
              <option key={code} value={code}>
                {label("currency", code)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="profile-note">
        {t("business.preview", { example: preview(draft.locale, draft.time_zone, draft.currency) })}
      </p>
      <p className="profile-note">{t("business.notBuilt")}</p>
      {canEdit ? null : <p className="profile-note">{t("business.readOnly")}</p>}
      {error ? (
        <div className="notice error row" role="alert">
          <p>{message[error]}</p>
          {error === "stale" ? (
            <Button size="sm" onPress={onReload}>
              {t("business.reload")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {canEdit ? (
        <div className="business-footer">
          <Button type="submit" variant="primary" isDisabled={!dirty || save.isPending}>
            {t("business.save")}
          </Button>
        </div>
      ) : null}
    </form>
  );
}
