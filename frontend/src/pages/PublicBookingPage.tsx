import { CircleCheckBig, Copy } from "lucide-react";
import { type RefObject, type SyntheticEvent, useEffect, useRef, useState } from "react";
import { useIntl } from "react-intl";

import { ApiError } from "../api/client";
import {
  type Booked,
  managePath,
  useBook,
  useFreeTimes,
  usePublicBookingPage,
  type Visitor,
  VisitorRefused,
} from "../api/bookingPages";
import { newIdempotencyKey } from "../api/records";
import { Loading } from "../components/StateNotice";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { KIND_LABEL, TimeRange } from "../records/appointmentParts";

/*
 * The hosted booking page (decision P5-C 5, 10): /app/b/<workspace>/<key>.
 * No app frame, no sign-in, nothing about the workspace or the host. Free
 * times come from the server a week at a time and are shown in the
 * visitor's own time zone, named. The booking goes to the public route
 * with one Idempotency-Key per chosen time, so a double click or a retry
 * books once; the hidden "website" field is the honeypot. The server
 * checks the time again: one taken meanwhile is refused and the times are
 * reloaded. The confirmation shows the visitor's private link once.
 */

const DAY = 86_400_000;

function startOfDay(date: Date): Date {
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return day;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function zoneName(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone.replaceAll("_", " ");
}

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "time_unavailable") return "publicBooking.error.taken";
    if (error.code === "booking_limit") return "publicBooking.error.limit";
    if (error.status === 404) return "publicBooking.error.gone";
    if (error.status === 429) return "publicForm.error.busy";
    if (error.status === 503) return "publicForm.error.unavailable";
  }
  return "publicBooking.error.failed";
}

const EMPTY: Visitor = { first_name: "", last_name: null, email: "", phone: null, message: null };
const FIELDS = [
  ["first_name", "publicBooking.firstName", "text", "given-name", true],
  ["last_name", "publicBooking.lastName", "text", "family-name", false],
  ["email", "publicBooking.email", "email", "email", true],
  ["phone", "publicBooking.phone", "tel", "tel", false],
] as const;

/** Blank optional details are sent as `null`. */
function cleaned(visitor: Visitor): Visitor {
  const blank = (value: string | null) => (value?.trim() ? value : null);
  return {
    ...visitor,
    last_name: blank(visitor.last_name),
    phone: blank(visitor.phone),
    message: blank(visitor.message),
  };
}

export function PublicBookingPage({ workspaceId, pageKey }: { workspaceId: string; pageKey: string }) {
  const t = useT();
  const intl = useIntl();
  const page = usePublicBookingPage(workspaceId, pageKey);
  const book = useBook(workspaceId, pageKey);
  const today = startOfDay(new Date());
  const [weekStart, setWeekStart] = useState(today);
  const weekEnd = addDays(weekStart, 7);
  const times = useFreeTimes(workspaceId, pageKey, weekStart, weekEnd, page.isSuccess);
  const [chosen, setChosen] = useState<string | null>(null);
  const [visitor, setVisitor] = useState<Visitor>(EMPTY);
  const [website, setWebsite] = useState("");
  const [attempt, setAttempt] = useState(newIdempotencyKey);
  // Fields changed since the last refusal no longer show its message.
  const [edited, setEdited] = useState<ReadonlySet<string>>(new Set());
  const confirmed = useRef<HTMLDivElement>(null);
  const refused = book.error instanceof VisitorRefused ? book.error.fields : {};

  useEffect(() => {
    if (book.isSuccess) confirmed.current?.focus();
  }, [book.isSuccess]);

  const choose = (time: string | null) => {
    setChosen(time);
    // A new time is a new attempt: its own Idempotency-Key.
    setAttempt(newIdempotencyKey());
    book.reset();
  };

  let body;
  if (page.isPending) {
    body = <Loading />;
  } else if (page.isError) {
    body = (
      <p className="notice error" role="alert">
        {t(failure(page.error))}
      </p>
    );
  } else if (book.isSuccess) {
    body = <Confirmation workspaceId={workspaceId} booked={book.data} focus={confirmed} />;
  } else {
    const lastDay = addDays(today, page.data.horizon_days);
    const byDay = new Map<string, string[]>();
    for (const time of times.data ?? []) {
      const day = startOfDay(new Date(time)).toISOString();
      byDay.set(day, [...(byDay.get(day) ?? []), time]);
    }
    const onSubmit = (event: SyntheticEvent) => {
      event.preventDefault();
      if (!chosen) return;
      setEdited(new Set());
      book.mutate(
        { startsAt: chosen, visitor: cleaned(visitor), website, attempt },
        {
          onError: (error) => {
            if (error.code === "time_unavailable") {
              setChosen(null);
              setAttempt(newIdempotencyKey());
            }
          },
        },
      );
    };
    body = (
      <>
        <h1 className="public-form-title">{page.data.name}</h1>
        <p className="muted">
          {t("publicBooking.with", { length: page.data.length_minutes, kind: t(KIND_LABEL[page.data.kind]) })}
        </p>
        {page.data.description ? <p className="booking-description">{page.data.description}</p> : null}
        {book.isError && !(book.error instanceof VisitorRefused) ? (
          <p className="notice error" role="alert">
            {t(failure(book.error))}
          </p>
        ) : null}
        {chosen ? (
          <form className="public-form" noValidate onSubmit={onSubmit} aria-labelledby="booking-details-title">
            <div className="booking-chosen">
              <TimeRange
                start={chosen}
                end={new Date(new Date(chosen).getTime() + page.data.length_minutes * 60_000).toISOString()}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  choose(null);
                }}
              >
                {t("publicBooking.change")}
              </button>
            </div>
            <h2 id="booking-details-title" className="booking-step-title">
              {t("publicBooking.details")}
            </h2>
            <p className="form-hint">{t("publicForm.requiredHint")}</p>
            {FIELDS.map(([name, label, type, autoComplete, required]) => {
              const code = edited.has(name) ? undefined : refused[name];
              const id = `booking-${name}`;
              return (
                <div key={name} className="form-field">
                  <label htmlFor={id} className="form-label">
                    {t(label)}
                    {required ? (
                      <span className="required" aria-hidden="true">
                        {" *"}
                      </span>
                    ) : null}
                  </label>
                  <input
                    id={id}
                    className="form-input"
                    type={type}
                    autoComplete={autoComplete}
                    required={required}
                    value={visitor[name] ?? ""}
                    aria-invalid={code ? true : undefined}
                    aria-describedby={code ? `${id}-error` : undefined}
                    onChange={(event) => {
                      setVisitor((current) => ({ ...current, [name]: event.target.value }));
                      setEdited((current) => new Set(current).add(name));
                    }}
                  />
                  {code ? (
                    <span id={`${id}-error`} className="form-error">
                      {t(code === "required" ? "publicBooking.error.required" : "publicBooking.error.invalid")}
                    </span>
                  ) : null}
                </div>
              );
            })}
            <div className="form-field">
              <label htmlFor="booking-message" className="form-label">
                {t("publicBooking.message")}
              </label>
              <textarea
                id="booking-message"
                className="form-input form-textarea"
                rows={3}
                maxLength={1000}
                value={visitor.message ?? ""}
                aria-invalid={!edited.has("message") && refused.message ? true : undefined}
                aria-describedby={!edited.has("message") && refused.message ? "booking-message-error" : undefined}
                onChange={(event) => {
                  setVisitor((current) => ({ ...current, message: event.target.value }));
                  setEdited((current) => new Set(current).add("message"));
                }}
              />
              {!edited.has("message") && refused.message ? (
                <span id="booking-message-error" className="form-error">
                  {t("publicBooking.error.invalid")}
                </span>
              ) : null}
            </div>
            <div className="public-honeypot" aria-hidden="true">
              <label htmlFor="booking-website">{t("publicForm.honeypot")}</label>
              <input
                id="booking-website"
                name="website"
                tabIndex={-1}
                autoComplete="off"
                value={website}
                onChange={(event) => {
                  setWebsite(event.target.value);
                }}
              />
            </div>
            {book.error instanceof VisitorRefused ? (
              <p className="notice error" role="alert">
                {t("publicBooking.error.check")}
              </p>
            ) : null}
            <button type="submit" className="btn btn-primary btn-lg public-submit" disabled={book.isPending}>
              {book.isPending ? t("publicBooking.sending") : t("publicBooking.submit")}
            </button>
          </form>
        ) : (
          <section className="booking-times" aria-labelledby="booking-times-title">
            <div className="booking-week">
              <h2 id="booking-times-title" className="booking-step-title">
                {t("publicBooking.pick")}
              </h2>
              <div className="booking-week-steps">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={weekStart.getTime() <= today.getTime()}
                  onClick={() => {
                    setWeekStart(addDays(weekStart, -7));
                  }}
                >
                  {t("publicBooking.earlier")}
                </button>
                <span className="booking-week-label" aria-live="polite">
                  {t("publicBooking.week", {
                    start: intl.formatDate(weekStart, { month: "short", day: "numeric" }),
                    end: intl.formatDate(addDays(weekEnd, -1), { month: "short", day: "numeric" }),
                  })}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={weekEnd.getTime() > lastDay.getTime() + DAY}
                  onClick={() => {
                    setWeekStart(weekEnd);
                  }}
                >
                  {t("publicBooking.later")}
                </button>
              </div>
            </div>
            <p className="form-hint">{t("publicBooking.zone", { zone: zoneName() })}</p>
            {times.isPending ? (
              <Loading />
            ) : times.isError ? (
              <p className="notice error" role="alert">
                {t("publicBooking.error.times")}
              </p>
            ) : byDay.size === 0 ? (
              <p className="muted">{t("publicBooking.noTimes")}</p>
            ) : (
              [...byDay.entries()].map(([day, starts]) => (
                <div key={day} className="booking-day">
                  <h3 className="booking-day-title">
                    {intl.formatDate(new Date(day), { weekday: "long", month: "long", day: "numeric" })}
                  </h3>
                  <ul className="booking-slots">
                    {starts.map((time) => (
                      <li key={time}>
                        <button
                          type="button"
                          className="booking-slot"
                          onClick={() => {
                            choose(time);
                          }}
                        >
                          {intl.formatTime(new Date(time), { hour: "numeric", minute: "2-digit" })}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))
            )}
          </section>
        )}
      </>
    );
  }
  return (
    <main id="main" className="public-form-page">
      <div className="public-form-card booking-card">{body}</div>
      <p className="public-form-foot">{t("publicBooking.footer")}</p>
    </main>
  );
}

function Confirmation({
  workspaceId,
  booked,
  focus,
}: {
  workspaceId: string;
  booked: Booked;
  focus: RefObject<HTMLDivElement | null>;
}) {
  const t = useT();
  const [copied, setCopied] = useState<boolean | null>(null);
  const link = booked.token ? `${window.location.origin}${managePath(workspaceId, booked.token)}` : null;
  return (
    <div className="public-thanks booking-confirmed" ref={focus} tabIndex={-1} role="status">
      <CircleCheckBig size={28} aria-hidden="true" />
      <h1 className="public-form-title">{t("publicBooking.confirmed")}</h1>
      {booked.booking.page_name ? <p>{booked.booking.page_name}</p> : null}
      <p>
        <TimeRange start={booked.booking.starts_at} end={booked.booking.ends_at} />
      </p>
      <p className="muted">{t(KIND_LABEL[booked.booking.kind])}</p>
      {booked.booking.location ? (
        <p className="booking-location">{t("publicBooking.location", { location: booked.booking.location })}</p>
      ) : null}
      {link ? (
        <div className="booking-manage">
          <p>{t("publicBooking.keepLink")}</p>
          <a className="booking-manage-link" href={link}>
            {link}
          </a>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              void navigator.clipboard.writeText(link).then(
                () => {
                  setCopied(true);
                },
                () => {
                  setCopied(false);
                },
              );
            }}
          >
            <Copy size={13} aria-hidden="true" />
            {t("bookingPages.copy")}
          </button>
          {copied === null ? null : <p className="muted">{t(copied ? "bookingPages.copied" : "bookingPages.copyFailed")}</p>}
        </div>
      ) : (
        <p className="muted">{t("publicBooking.noLink")}</p>
      )}
    </div>
  );
}
