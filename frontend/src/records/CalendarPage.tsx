import { CalendarPlus, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Button as AriaButton } from "react-aria-components";
import { useIntl } from "react-intl";

import {
  addDays,
  type Appointment,
  type Availability,
  closedSpans,
  isOpen,
  lanes,
  minutesInto,
  onDay,
  sameDay,
  startOfDay,
  step,
  timeZoneName,
  useAppointment,
  useAppointments,
  useAvailability,
  useUpcoming,
  type View,
  viewDays,
} from "../api/appointments";
import { useAccess, useMe, useMembers } from "../api/queries";
import { LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import {
  AppointmentDialog,
  AppointmentDrawer,
  type Draft,
  hostColour,
  STATUS_LABEL,
  TimeRange,
} from "./appointmentParts";
import { BookingPagesDrawer } from "./BookingPages";
import { type Option, ownerOptions } from "./parts";

/*
 * Calendar (ScreenCalendar.dc.html, decision P5-A): Day, Week and Month
 * views with previous, Today and next; a side panel (wide screens) with the
 * team filter and today's count per member, "Up next" and the status
 * legend; a week column per day, a day column per member, a month cell per
 * day with up to three appointments. Clicking a free half hour books at that
 * time; keyboard users book with "New appointment". Times are the viewer's
 * own time zone, which the header names. The grid shows the whole day and
 * opens at 07:00. Appointments shorter than 45 minutes show on one line.
 *
 * Business hours (decision P5-B) hatch the closed time and give each team
 * member a status line from today's appointments: in an appointment until
 * its end, outside business hours, or free. Nothing is hatched while the
 * workspace has not set its hours.
 */

const HOUR = 56; // pixels per hour, as in the design
const OPEN_AT = 7; // the hour the grid scrolls to
const VIEWS: [View, MessageId][] = [
  ["day", "calendar.view.day"],
  ["week", "calendar.view.week"],
  ["month", "calendar.view.month"],
];
const LEGEND: Appointment["status"][] = ["confirmed", "pending", "completed", "no_show"];

export function CalendarPage({
  workspaceId,
  openId,
  onOpen,
  onOpenContact,
}: {
  workspaceId: string;
  openId: string | null;
  onOpen: (id: string | null) => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const intl = useIntl();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const can = (action: string) => access.data?.actions[action] === true;
  const [view, setView] = useState<View>(() => (window.innerWidth < 760 ? "day" : "week"));
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<Appointment | null>(null);
  const [bookingPages, setBookingPages] = useState(false);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date());
    }, 60_000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  // An appointment opened from elsewhere (a contact's list) brings its day into view.
  const linked = useAppointment(workspaceId, openId);
  const linkedStart = linked.data?.starts_at;
  const [shownLinked, setShownLinked] = useState<string | undefined>(undefined);
  if (linkedStart && linkedStart !== shownLinked) {
    setShownLinked(linkedStart);
    setAnchor(startOfDay(new Date(linkedStart)));
  }

  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const hosts: Option[] = owners.length ? owners : meId ? [{ id: meId, label: t("records.owner.me") }] : [];
  const days = useMemo(() => viewDays(view, anchor), [view, anchor]);
  const first = days[0] ?? anchor;
  const end = addDays(days[days.length - 1] ?? anchor, 1);
  const range = useAppointments(workspaceId, first, end);
  const hours = useAvailability(workspaceId, first, end);
  const items = (range.data?.items ?? []).filter((a) => !hidden.has(a.host_user_id));
  const today = startOfDay(now);
  // Today's own queries: the side panel speaks of today whichever range is in view.
  const todayRange = useAppointments(workspaceId, today, addDays(today, 1));
  const todayHours = useAvailability(workspaceId, today, addDays(today, 1));
  const todays = onDay(todayRange.data?.items ?? [], today);

  const label =
    view === "month"
      ? intl.formatDate(anchor, { month: "long", year: "numeric" })
      : view === "day"
        ? intl.formatDate(anchor, { weekday: "long", month: "long", day: "numeric", year: "numeric" })
        : `${intl.formatDate(first, { month: "short", day: "numeric" })} – ${intl.formatDate(addDays(end, -1), { month: "short", day: "numeric", year: "numeric" })}`;

  const book = (start: Date, host?: string) => {
    if (!can("create_appointment")) return;
    setDraft({ start, host });
  };
  const visibleHosts = hosts.filter((h) => !hidden.has(h.id));

  return (
    <div className="records-page calendar-page">
      <div className="calendar-toolbar">
        <h1 className="records-title">{t("nav.calendar")}</h1>
        <div className="calendar-steps">
          <AriaButton
            className="icon-button bordered"
            aria-label={t("calendar.previous")}
            onPress={() => {
              setAnchor(step(view, anchor, -1));
            }}
          >
            <ChevronLeft size={15} aria-hidden="true" />
          </AriaButton>
          <Button
            size="sm"
            onPress={() => {
              setAnchor(startOfDay(new Date()));
            }}
          >
            {t("calendar.today")}
          </Button>
          <AriaButton
            className="icon-button bordered"
            aria-label={t("calendar.next")}
            onPress={() => {
              setAnchor(step(view, anchor, 1));
            }}
          >
            <ChevronRight size={15} aria-hidden="true" />
          </AriaButton>
        </div>
        <h2 className="calendar-range" aria-live="polite">
          {label}
        </h2>
        <span className="calendar-zone muted">{t("calendar.zone", { zone: timeZoneName() })}</span>
        <div className="calendar-spacer" />
        <div className="segmented" role="group" aria-label={t("calendar.views")}>
          {VIEWS.map(([key, text]) => (
            <AriaButton
              key={key}
              className={view === key ? "segment active" : "segment"}
              aria-pressed={view === key}
              onPress={() => {
                setView(key);
              }}
            >
              {t(text)}
            </AriaButton>
          ))}
        </div>
        {can("read_booking_pages") ? (
          <Button
            onPress={() => {
              setBookingPages(true);
            }}
          >
            <CalendarPlus size={15} aria-hidden="true" />
            {t("bookingPages.open")}
          </Button>
        ) : null}
        {can("create_appointment") ? (
          <Button
            variant="primary"
            onPress={() => {
              // The next full hour today, or 09:00 on the day in view.
              const start = new Date(sameDay(anchor, now) ? now : anchor);
              start.setHours(sameDay(anchor, now) ? now.getHours() + 1 : 9, 0, 0, 0);
              book(start);
            }}
          >
            <Plus size={15} aria-hidden="true" />
            {t("appointments.new")}
          </Button>
        ) : null}
      </div>

      {range.isError ? <LoadError error={range.error} onRetry={() => void range.refetch()} /> : null}
      {range.data?.truncated ? (
        <p className="notice records-notice" role="status">
          {t("calendar.truncated")}
        </p>
      ) : null}

      <div className="calendar-body">
        <aside className="calendar-side" aria-label={t("calendar.side")}>
          <h2 className="calendar-side-title">{t("calendar.team")}</h2>
          <ul className="calendar-team">
            {hosts.map((host) => {
              const shown = !hidden.has(host.id);
              const mine = todays.filter((a) => a.host_user_id === host.id);
              const current = mine.find((a) => new Date(a.starts_at) <= now && now < new Date(a.ends_at));
              const [tone, presence] = current
                ? ["busy", t("calendar.busyUntil", { time: intl.formatTime(new Date(current.ends_at)) })]
                : isOpen(todayHours.data, now)
                  ? ["free", t("calendar.freeNow")]
                  : ["closed", t("calendar.closedNow")];
              return (
                <li key={host.id}>
                  <label className="calendar-person">
                    <input
                      type="checkbox"
                      checked={shown}
                      onChange={() => {
                        setHidden((before) => {
                          const next = new Set(before);
                          if (shown) next.add(host.id);
                          else next.delete(host.id);
                          return next;
                        });
                      }}
                    />
                    <span className="calendar-swatch" style={{ background: hostColour(host.id) }} aria-hidden="true" />
                    <span className="calendar-person-text">
                      <span className="calendar-person-name">{host.label}</span>
                      <span className={`calendar-presence ${tone}`}>{presence}</span>
                    </span>
                    <span className="calendar-load">{t("calendar.todayCount", { count: mine.length })}</span>
                  </label>
                </li>
              );
            })}
          </ul>
          <UpNext
            workspaceId={workspaceId}
            onOpen={(id) => {
              onOpen(id);
            }}
          />
          <h2 className="calendar-side-title">{t("calendar.legend")}</h2>
          <ul className="calendar-legend">
            {LEGEND.map((status) => (
              <li key={status}>
                <span className={`legend-chip ${status}`} aria-hidden="true" />
                {t(STATUS_LABEL[status])}
              </li>
            ))}
            {hours.data?.hours_set ? (
              <li>
                <span className="legend-chip closed" aria-hidden="true" />
                {t("calendar.closed")}
              </li>
            ) : null}
          </ul>
        </aside>

        <div className="calendar-main">
          {view === "month" ? (
            <MonthGrid
              days={days}
              month={anchor.getMonth()}
              today={today}
              items={items}
              onDay={(day) => {
                setAnchor(day);
                setView("day");
              }}
              onOpen={onOpen}
            />
          ) : (
            <TimeGrid
              columns={
                view === "week"
                  ? days.map((day) => ({ key: day.toISOString(), day, host: undefined, head: <DayHead day={day} today={today} /> }))
                  : (visibleHosts.length ? visibleHosts : [{ id: "", label: t("calendar.everyone") }]).map((host) => ({
                      key: host.id || "all",
                      day: first,
                      host: host.id || undefined,
                      head: <PersonHead host={host} />,
                    }))
              }
              items={items}
              availability={hours.data}
              now={now}
              canBook={can("create_appointment")}
              onBook={book}
              onOpen={onOpen}
            />
          )}
        </div>
      </div>

      {openId ? (
        <AppointmentDrawer
          workspaceId={workspaceId}
          id={openId}
          meId={meId}
          canUpdate={can("update_appointment")}
          canDelete={can("delete_appointment")}
          onClose={() => {
            onOpen(null);
          }}
          onEdit={setEditing}
          onOpenContact={onOpenContact}
        />
      ) : null}
      {bookingPages ? (
        <BookingPagesDrawer
          workspaceId={workspaceId}
          hosts={hosts}
          meId={meId}
          canManage={can("manage_booking_pages")}
          onClose={() => {
            setBookingPages(false);
          }}
        />
      ) : null}
      {draft || editing ? (
        <AppointmentDialog
          workspaceId={workspaceId}
          appointment={editing ?? undefined}
          draft={draft ?? undefined}
          hosts={hosts}
          meId={meId}
          onClose={() => {
            setDraft(null);
            setEditing(null);
          }}
          onSaved={(saved) => {
            if (!editing) setAnchor(startOfDay(new Date(saved.starts_at)));
          }}
        />
      ) : null}
    </div>
  );
}

function DayHead({ day, today }: { day: Date; today: Date }) {
  const intl = useIntl();
  const isToday = sameDay(day, today);
  return (
    <span className={isToday ? "calendar-day-head today" : "calendar-day-head"}>
      <span className="calendar-dow">{intl.formatDate(day, { weekday: "short" })}</span>
      <span className="calendar-date">{intl.formatDate(day, { day: "numeric" })}</span>
    </span>
  );
}

function PersonHead({ host }: { host: Option }) {
  return (
    <span className="calendar-day-head">
      <span className="calendar-swatch" style={{ background: host.id ? hostColour(host.id) : "#8A91A0" }} aria-hidden="true" />
      <span className="calendar-person-name">{host.label}</span>
    </span>
  );
}

interface Column {
  key: string;
  day: Date;
  host: string | undefined;
  head: ReactNode;
}

function TimeGrid({
  columns,
  items,
  availability,
  now,
  canBook,
  onBook,
  onOpen,
}: {
  columns: Column[];
  items: Appointment[];
  availability: Availability | undefined;
  now: Date;
  canBook: boolean;
  onBook: (start: Date, host?: string) => void;
  onOpen: (id: string) => void;
}) {
  const intl = useIntl();
  const t = useT();
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = OPEN_AT * HOUR - 12; // the hour's label shows too
  }, []);
  const hours = Array.from({ length: 24 }, (_, h) => h);
  return (
    <div className="calendar-scroll" ref={scroller}>
      <div className="calendar-grid" style={{ minWidth: columns.length > 1 ? `${String(60 + columns.length * 112)}px` : undefined }}>
        <div className="calendar-head-row">
          <div className="calendar-gutter" />
          {columns.map((column) => (
            <div key={column.key} className="calendar-col-head">
              {column.head}
            </div>
          ))}
        </div>
        <div className="calendar-rows">
          <div className="calendar-gutter">
            {hours.map((h) => (
              <div key={h} className="calendar-hour" style={{ height: HOUR }}>
                {h === 0 ? "" : intl.formatTime(new Date(2026, 0, 1, h), { hour: "numeric" })}
              </div>
            ))}
          </div>
          {columns.map((column) => {
            const placed = lanes(
              onDay(items, column.day).filter((a) => column.host === undefined || a.host_user_id === column.host),
            );
            const isToday = sameDay(column.day, now);
            return (
              <div key={column.key} className="calendar-col" style={{ height: 24 * HOUR }}>
                {closedSpans(column.day, availability).map(([from, to]) => (
                  <div
                    key={from}
                    className="calendar-closed"
                    style={{ top: (from / 60) * HOUR, height: ((to - from) / 60) * HOUR }}
                    aria-hidden="true"
                  />
                ))}
                {canBook ? (
                  // Clicking a free half hour books at that time, for pointer
                  // users; keyboard users book with "New appointment".
                  <div
                    className="calendar-hit"
                    title={t("calendar.clickToBook")}
                    aria-hidden="true"
                    onClick={(event) => {
                      const offset = event.clientY - event.currentTarget.getBoundingClientRect().top;
                      const half = Math.max(0, Math.min(47, Math.floor(offset / (HOUR / 2))));
                      const start = new Date(column.day);
                      start.setHours(Math.floor(half / 2), (half % 2) * 30, 0, 0);
                      onBook(start, column.host);
                    }}
                  />
                ) : null}
                {placed.map(({ appointment, lane, lanes: count }) => {
                  const top = (minutesInto(column.day, new Date(appointment.starts_at)) / 60) * HOUR;
                  const bottom = (minutesInto(column.day, new Date(appointment.ends_at)) / 60) * HOUR;
                  return (
                    <AriaButton
                      key={appointment.id}
                      className={`calendar-event ${appointment.status}${bottom - top < 40 ? " short" : ""}`}
                      style={{
                        top: top + 1,
                        height: Math.max(bottom - top - 3, 18),
                        left: `calc(${String((lane / count) * 100)}% + 3px)`,
                        width: `calc(${String(100 / count)}% - 6px)`,
                        borderLeftColor: hostColour(appointment.host_user_id),
                      }}
                      onPress={() => {
                        onOpen(appointment.id);
                      }}
                    >
                      <span className="calendar-event-title">{appointment.title}</span>
                      <span className="calendar-event-meta">
                        <TimeRange start={appointment.starts_at} end={appointment.ends_at} withDate={false} />
                        {appointment.contact ? ` · ${appointment.contact.name}` : ""}
                        <span className="sr-only">{` · ${t(STATUS_LABEL[appointment.status])}`}</span>
                      </span>
                    </AriaButton>
                  );
                })}
                {isToday ? (
                  <div className="calendar-now" style={{ top: (minutesInto(column.day, now) / 60) * HOUR }} aria-hidden="true" />
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MonthGrid({
  days,
  month,
  today,
  items,
  onDay: openDay,
  onOpen,
}: {
  days: Date[];
  month: number;
  today: Date;
  items: Appointment[];
  onDay: (day: Date) => void;
  onOpen: (id: string) => void;
}) {
  const intl = useIntl();
  const t = useT();
  const weekdays = days.slice(0, 7);
  return (
    <div className="calendar-scroll">
      <div className="calendar-month">
        {weekdays.map((day) => (
          <div key={`dow-${day.toISOString()}`} className="calendar-month-dow">
            {intl.formatDate(day, { weekday: "short" })}
          </div>
        ))}
        {days.map((day) => {
          const chips = onDay(items, day);
          const outside = day.getMonth() !== month;
          return (
            <div key={day.toISOString()} className={outside ? "calendar-month-cell outside" : "calendar-month-cell"}>
              <AriaButton
                className={sameDay(day, today) ? "calendar-month-num today" : "calendar-month-num"}
                aria-label={t("calendar.openDay", {
                  day: intl.formatDate(day, { weekday: "long", month: "long", day: "numeric" }),
                  count: chips.length,
                })}
                onPress={() => {
                  openDay(day);
                }}
              >
                {intl.formatDate(day, { day: "numeric" })}
              </AriaButton>
              {chips.slice(0, 3).map((a) => (
                <AriaButton
                  key={a.id}
                  className={`calendar-chip ${a.status}`}
                  style={{ borderLeftColor: hostColour(a.host_user_id) }}
                  onPress={() => {
                    onOpen(a.id);
                  }}
                >
                  {intl.formatTime(new Date(a.starts_at), { hour: "numeric", minute: "2-digit" })} {a.title}
                </AriaButton>
              ))}
              {chips.length > 3 ? (
                <span className="calendar-more">{t("calendar.more", { count: chips.length - 3 })}</span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function UpNext({
  workspaceId,
  onOpen,
}: {
  workspaceId: string;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const upcoming = useUpcoming(workspaceId);
  const items = upcoming.data ?? [];
  return (
    <>
      <h2 className="calendar-side-title">{t("calendar.upNext")}</h2>
      {items.length ? (
        <ul className="calendar-upnext">
          {items.map((a) => (
            <li key={a.id}>
              <AriaButton
                className="calendar-upnext-item"
                onPress={() => {
                  onOpen(a.id);
                }}
              >
                <span className="calendar-swatch tall" style={{ background: hostColour(a.host_user_id) }} aria-hidden="true" />
                <span>
                  <span className="calendar-upnext-title">{a.title}</span>
                  <span className="calendar-upnext-meta">
                    <TimeRange start={a.starts_at} end={a.ends_at} />
                    {a.contact ? ` · ${a.contact.name}` : ""}
                  </span>
                </span>
              </AriaButton>
            </li>
          ))}
        </ul>
      ) : upcoming.isPending ? null : (
        <p className="muted calendar-side-empty">{t("calendar.nothingNext")}</p>
      )}
    </>
  );
}
