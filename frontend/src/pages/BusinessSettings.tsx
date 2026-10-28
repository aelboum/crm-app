import { type SyntheticEvent, useState } from "react";
import { useIntl } from "react-intl";

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
 * how to show them. Business hours (decision P5-B): a switch and one range
 * per day, Monday first, in the workspace's time zone; not set until saved
 * (Monday to Friday 09:00-17:00 is offered as a start) and can be cleared.
 * The design's phone, email, website and address have no backend yet and
 * are named as unavailable; the workspace name is shown but cannot be
 * changed (SaaS-OS offers no rename).
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

type Draft = Pick<WorkspaceSettings, "locale" | "time_zone" | "currency" | "business_hours">;
type Week = NonNullable<WorkspaceSettings["business_hours"]>;
type Day = Week[number];

const WORKDAY = { opens: "09:00", closes: "17:00" };
const SUGGESTED: Week = [WORKDAY, WORKDAY, WORKDAY, WORKDAY, WORKDAY, null, null];

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
/** A day the server accepts: closed, or HH:MM times with the opening first. */
const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;
const validDay = (day: Day) => day === null || (CLOCK.test(day.opens) && CLOCK.test(day.closes) && day.opens < day.closes);

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
    business_hours: saved.business_hours,
  });
  const [error, setError] = useState<"stale" | "invalid" | "denied" | "generic" | null>(null);
  const changes = Object.fromEntries(
    (Object.keys(draft) as (keyof Draft)[])
      .filter((name) => !same(draft[name], saved[name]))
      .map((name) => [name, draft[name]]),
  );
  const hoursValid = (draft.business_hours ?? []).every(validDay);
  const dirty = Object.keys(changes).length > 0;

  function set(name: keyof Draft, value: Draft[keyof Draft]) {
    setDraft((current) => ({ ...current, [name]: value }));
    setError(null);
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (!dirty || !hoursValid) return;
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
      <BusinessHours
        week={draft.business_hours}
        zone={draft.time_zone}
        canEdit={canEdit}
        onChange={(week) => {
          set("business_hours", week);
        }}
      />
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
          <Button type="submit" variant="primary" isDisabled={!dirty || !hoursValid || save.isPending}>
            {t("business.save")}
          </Button>
        </div>
      ) : null}
    </form>
  );
}

/** The business hours editor (P5-B 8): a switch and two times a day. */
function BusinessHours({
  week,
  zone,
  canEdit,
  onChange,
}: {
  week: Week | null;
  zone: string;
  canEdit: boolean;
  onChange: (week: Week | null) => void;
}) {
  const t = useT();
  const intl = useIntl();
  // 5 January 2026 is a Monday.
  const weekday = (index: number) => intl.formatDate(new Date(2026, 0, 5 + index), { weekday: "long" });
  const setDay = (index: number, day: Day) => {
    if (week) onChange(week.map((current, i) => (i === index ? day : current)));
  };
  return (
    <section className="hours-section" aria-labelledby="business-hours-title">
      <div className="hours-head">
        <h2 id="business-hours-title" className="field-label">
          {t("business.hours")}
        </h2>
        {canEdit && week ? (
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              onChange(null);
            }}
          >
            {t("business.hoursClear")}
          </Button>
        ) : null}
      </div>
      {week ? (
        <ul className="hours-list">
          {week.map((day, index) => {
            const name = weekday(index);
            return (
              <li key={name} className="hours-row">
                <label className="hours-day">
                  <input
                    type="checkbox"
                    role="switch"
                    checked={day !== null}
                    disabled={!canEdit}
                    onChange={(event) => {
                      setDay(index, event.target.checked ? WORKDAY : null);
                    }}
                  />
                  {name}
                </label>
                {day ? (
                  <span className="hours-times">
                    <input
                      type="time"
                      step={900}
                      className="field-input"
                      aria-label={t("business.opens", { day: name })}
                      value={day.opens}
                      disabled={!canEdit}
                      aria-invalid={!validDay(day)}
                      onChange={(event) => {
                        setDay(index, { ...day, opens: event.target.value });
                      }}
                    />
                    <span aria-hidden="true">–</span>
                    <input
                      type="time"
                      step={900}
                      className="field-input"
                      aria-label={t("business.closes", { day: name })}
                      value={day.closes}
                      disabled={!canEdit}
                      aria-invalid={!validDay(day)}
                      onChange={(event) => {
                        setDay(index, { ...day, closes: event.target.value });
                      }}
                    />
                  </span>
                ) : (
                  <span className="hours-closed">{t("business.closedDay")}</span>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="hours-unset">
          <p className="profile-note">{t("business.hoursUnset")}</p>
          {canEdit ? (
            <Button
              size="sm"
              onPress={() => {
                onChange(SUGGESTED);
              }}
            >
              {t("business.hoursSet")}
            </Button>
          ) : null}
        </div>
      )}
      {week && !week.every(validDay) ? (
        <p className="notice error" role="alert">
          {t("business.hoursInvalid")}
        </p>
      ) : null}
      <p className="profile-note">{t("business.hoursZone", { zone: zone.replaceAll("_", " ") })}</p>
    </section>
  );
}
