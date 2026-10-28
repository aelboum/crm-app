import { CalendarClock, MapPin, Pencil, Phone, Trash2, TriangleAlert, Video } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { Button as AriaButton } from "react-aria-components";
import { useIntl } from "react-intl";

import {
  type Appointment,
  type AppointmentChanges,
  type Conflict,
  ConflictRefusal,
  type Kind,
  KINDS,
  LENGTHS,
  localInput,
  type Status,
  STATUSES,
  useAppointment,
  useConflicts,
  useCreateAppointment,
  useDeleteAppointment,
  useUpdateAppointment,
} from "../api/appointments";
import { ApiError } from "../api/client";
import { FieldErrors, newIdempotencyKey } from "../api/records";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { CompanyPicker, type PickedCompany } from "./CompanyPicker";
import { Drawer, FieldRow, type Option, ownerLabel } from "./parts";

/*
 * Pieces shared by the Calendar and the contact drawer's appointments
 * (decision P5-A): labels and colours, the booking dialog with its live
 * conflict check (a conflict turns "Book" into "Book anyway", which the
 * server then allows), and the appointment drawer with the design's status
 * buttons, its details, Edit, Cancel (a status, after a confirmation) and,
 * for Owners and Admins, Delete. Each change sends the appointment's
 * version; the server decides.
 */

export const KIND_LABEL: Record<Kind, MessageId> = {
  in_person: "appointments.kind.in_person",
  video: "appointments.kind.video",
  phone: "appointments.kind.phone",
};

export const STATUS_LABEL: Record<Status, MessageId> = {
  confirmed: "appointments.status.confirmed",
  pending: "appointments.status.pending",
  completed: "appointments.status.completed",
  no_show: "appointments.status.no_show",
  cancelled: "appointments.status.cancelled",
};

export const STATUS_TONE: Record<Status, Tone> = {
  confirmed: "success",
  pending: "pending",
  completed: "neutral",
  no_show: "risk",
  cancelled: "neutral",
};

const KIND_ICON = { in_person: MapPin, video: Video, phone: Phone } as const;

/** The design's host colours, chosen by the member's ID so each keeps one. */
const HOST_COLOURS = ["#3B6FD9", "#1F8A4C", "#B7791F", "#8A4FD1", "#C2410C", "#0E7490", "#BE185D", "#4D7C0F"];

export function hostColour(userId: string): string {
  let hash = 0;
  for (const char of userId) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return HOST_COLOURS[hash % HOST_COLOURS.length] ?? "#3B6FD9";
}

const REFUSALS: Record<string, MessageId> = {
  stale_version: "appointments.error.version",
  appointment_not_found: "appointments.error.gone",
  appointment_cancelled: "appointments.error.cancelled",
  contact_not_found: "appointments.error.contact",
  host_not_member: "appointments.error.host",
  invalid_times: "appointments.error.times",
};

export function appointmentRefusal(error: unknown): MessageId {
  if (error instanceof FieldErrors) return "appointments.error.fields";
  if (error instanceof ApiError) {
    const known = error.code ? REFUSALS[error.code] : undefined;
    if (known) return known;
    if (error.status === 403) return "appointments.error.forbidden";
  }
  return "appointments.error.failed";
}

/** "Wed, Oct 28 · 9:00 – 9:30 AM", in the viewer's locale and time zone. */
export function TimeRange({ start, end, withDate = true }: { start: string; end: string; withDate?: boolean }) {
  const intl = useIntl();
  const from = new Date(start);
  const to = new Date(end);
  const time = (d: Date) => intl.formatTime(d, { hour: "numeric", minute: "2-digit" });
  const date = withDate ? `${intl.formatDate(from, { weekday: "short", month: "short", day: "numeric" })} · ` : "";
  const other = from.toDateString() === to.toDateString() ? "" : `${intl.formatDate(to, { month: "short", day: "numeric" })} `;
  return (
    <time dateTime={start}>
      {date}
      {time(from)} – {other}
      {time(to)}
    </time>
  );
}

function ConflictList({ conflicts }: { conflicts: Conflict[] }) {
  const t = useT();
  return (
    <div className="calendar-conflict">
      <TriangleAlert size={14} aria-hidden="true" />
      <div>
        <p>{t("appointments.conflict", { count: conflicts.length })}</p>
        <ul>
          {conflicts.map((c) => (
            <li key={c.id}>
              {c.title} · <TimeRange start={c.starts_at} end={c.ends_at} withDate={false} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export interface Draft {
  start: Date;
  host?: string | undefined;
  contact?: PickedCompany | null | undefined;
}

/**
 * Book a new appointment (`draft`) or edit one (`appointment`). The length is
 * one of the offered lengths; an edited appointment keeps its own length
 * among them.
 */
export function AppointmentDialog({
  workspaceId,
  appointment,
  draft,
  hosts,
  meId,
  onClose,
  onSaved,
}: {
  workspaceId: string;
  appointment?: Appointment | undefined;
  draft?: Draft | undefined;
  hosts: Option[];
  meId: string | undefined;
  onClose: () => void;
  onSaved?: (appointment: Appointment) => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateAppointment(workspaceId);
  const update = useUpdateAppointment(workspaceId);
  const startAt = appointment ? new Date(appointment.starts_at) : (draft?.start ?? new Date());
  const initialLength = appointment
    ? Math.round((new Date(appointment.ends_at).getTime() - startAt.getTime()) / 60_000)
    : 30;
  const [title, setTitle] = useState(appointment?.title ?? "");
  const [start, setStart] = useState(localInput(startAt));
  const [length, setLength] = useState(initialLength);
  const [host, setHost] = useState(appointment?.host_user_id ?? draft?.host ?? meId ?? hosts[0]?.id ?? "");
  const [contact, setContact] = useState<PickedCompany | null>(appointment?.contact ?? draft?.contact ?? null);
  const [kind, setKind] = useState<Kind>(appointment?.kind ?? "in_person");
  const [location, setLocation] = useState(appointment?.location ?? "");
  const [note, setNote] = useState(appointment?.note ?? "");
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const [refused, setRefused] = useState<Conflict[] | null>(null);
  const [key] = useState(newIdempotencyKey);
  const lengths = LENGTHS.includes(length) ? LENGTHS : [...LENGTHS, length].sort((a, b) => a - b);
  const hostChoices = hosts.some((option) => option.id === host)
    ? hosts
    : [...hosts, { id: host, label: ownerLabel(t, host, meId) }];

  const startDate = start ? new Date(start) : null;
  const valid = startDate !== null && !Number.isNaN(startDate.getTime()) && host !== "";
  const endDate = valid ? new Date(startDate.getTime() + length * 60_000) : null;
  const check = useConflicts(
    workspaceId,
    valid && endDate
      ? { host, start: startDate.toISOString(), end: endDate.toISOString(), exclude: appointment?.id ?? null }
      : null,
  );
  const conflicts = refused ?? check.data ?? [];
  const busy = create.isPending || update.isPending;

  const failed = (error: unknown) => {
    if (error instanceof ConflictRefusal) {
      setRefused(error.conflicts);
      setRefusal(null);
      return;
    }
    setRefusal(appointmentRefusal(error));
  };

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const text = title.trim();
    if (!text) {
      setRefusal("appointments.error.title");
      return;
    }
    if (!valid || !endDate) {
      setRefusal("appointments.error.times");
      return;
    }
    const allow = conflicts.length > 0;
    const values = {
      title: text,
      starts_at: startDate.toISOString(),
      ends_at: endDate.toISOString(),
      kind,
      location: location.trim() || null,
      note: note.trim() || null,
      host_user_id: host,
      contact_id: contact?.id ?? null,
    };
    const done = (saved: Appointment) => {
      toast(t(appointment ? "records.saved" : "appointments.booked"));
      onSaved?.(saved);
      onClose();
    };
    if (!appointment) {
      create.mutate(
        { body: { ...values, status: "confirmed", allow_conflict: allow }, key },
        { onSuccess: done, onError: failed },
      );
      return;
    }
    const changes: AppointmentChanges = {};
    if (values.title !== appointment.title) changes.title = values.title;
    if (new Date(values.starts_at).getTime() !== new Date(appointment.starts_at).getTime()) {
      changes.starts_at = values.starts_at;
    }
    if (new Date(values.ends_at).getTime() !== new Date(appointment.ends_at).getTime()) changes.ends_at = values.ends_at;
    if (values.kind !== appointment.kind) changes.kind = values.kind;
    if (values.location !== appointment.location) changes.location = values.location;
    if (values.note !== appointment.note) changes.note = values.note;
    if (values.host_user_id !== appointment.host_user_id) changes.host_user_id = values.host_user_id;
    if (values.contact_id !== appointment.contact_id) changes.contact_id = values.contact_id;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    update.mutate(
      { id: appointment.id, version: appointment.version, changes, allowConflict: allow },
      { onSuccess: done, onError: failed },
    );
  };

  const reset = () => {
    setRefused(null);
  };

  const submitLabel: MessageId = conflicts.length
    ? appointment
      ? "appointments.saveAnyway"
      : "appointments.bookAnyway"
    : appointment
      ? "records.saveChanges"
      : "appointments.book";

  return (
    <Dialog
      isOpen
      title={t(appointment ? "appointments.editTitle" : "appointments.newTitle")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="appointment-form" isDisabled={busy}>
            {t(submitLabel)}
          </Button>
        </>
      }
    >
      <form id="appointment-form" className="record-form" onSubmit={submit} noValidate>
        <div className="form-field wide">
          <label htmlFor="appointment-title" className="form-label">
            {t("appointments.field.title")}
          </label>
          <input
            id="appointment-title"
            className="form-input"
            value={title}
            maxLength={200}
            onChange={(event) => {
              setTitle(event.target.value);
            }}
          />
        </div>
        <CompanyPicker
          workspaceId={workspaceId}
          kind="contacts"
          id="appointment-contact"
          label={t("appointments.field.contact")}
          selected={contact}
          onChange={setContact}
        />
        <div className="form-field">
          <label htmlFor="appointment-host" className="form-label">
            {t("appointments.field.host")}
          </label>
          <select
            id="appointment-host"
            className="form-input form-select"
            value={host}
            onChange={(event) => {
              setHost(event.target.value);
              reset();
            }}
          >
            {hostChoices.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="appointment-start" className="form-label">
            {t("appointments.field.start")}
          </label>
          <input
            id="appointment-start"
            className="form-input"
            type="datetime-local"
            step={300}
            value={start}
            onChange={(event) => {
              setStart(event.target.value);
              reset();
            }}
          />
        </div>
        <div className="form-field">
          <label htmlFor="appointment-length" className="form-label">
            {t("appointments.field.length")}
          </label>
          <select
            id="appointment-length"
            className="form-input form-select"
            value={length}
            onChange={(event) => {
              setLength(Number(event.target.value));
              reset();
            }}
          >
            {lengths.map((minutes) => (
              <option key={minutes} value={minutes}>
                {t("appointments.minutes", { minutes })}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="form-field wide appointment-kinds">
          <legend className="form-label">{t("appointments.field.kind")}</legend>
          <div className="kind-choices">
            {KINDS.map((value) => {
              const Icon = KIND_ICON[value];
              return (
                <label key={value} className={kind === value ? "kind-choice active" : "kind-choice"}>
                  <input
                    type="radio"
                    name="appointment-kind"
                    value={value}
                    checked={kind === value}
                    onChange={() => {
                      setKind(value);
                    }}
                  />
                  <Icon size={14} aria-hidden="true" />
                  {t(KIND_LABEL[value])}
                </label>
              );
            })}
          </div>
        </fieldset>
        <div className="form-field wide">
          <label htmlFor="appointment-location" className="form-label">
            {t("appointments.field.location")}
          </label>
          <input
            id="appointment-location"
            className="form-input"
            value={location}
            maxLength={300}
            onChange={(event) => {
              setLocation(event.target.value);
            }}
          />
        </div>
        <div className="form-field wide">
          <label htmlFor="appointment-note" className="form-label">
            {t("appointments.field.note")}
          </label>
          <textarea
            id="appointment-note"
            className="form-input form-textarea"
            rows={3}
            value={note}
            maxLength={2000}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
        </div>
        <div className="form-field wide" role="status">
          {conflicts.length ? (
            <ConflictList conflicts={conflicts} />
          ) : valid && check.isSuccess ? (
            <p className="calendar-free">{t("appointments.free")}</p>
          ) : null}
        </div>
        {refusal ? (
          <p className="notice error form-field wide" role="alert">
            {t(refusal)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

/** The design's appointment drawer. */
export function AppointmentDrawer({
  workspaceId,
  id,
  meId,
  canUpdate,
  canDelete,
  onClose,
  onEdit,
  onOpenContact,
}: {
  workspaceId: string;
  id: string;
  meId: string | undefined;
  canUpdate: boolean;
  canDelete: boolean;
  onClose: () => void;
  onEdit: (appointment: Appointment) => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const query = useAppointment(workspaceId, id);
  const update = useUpdateAppointment(workspaceId);
  const remove = useDeleteAppointment(workspaceId);
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const [confirming, setConfirming] = useState<"cancel" | "delete" | null>(null);
  const appointment = query.data;
  const busy = update.isPending || remove.isPending;
  const open = appointment !== undefined && appointment.status !== "cancelled";

  function setStatus(status: Status) {
    if (!appointment || status === appointment.status) return;
    setRefusal(null);
    update.mutate(
      { id: appointment.id, version: appointment.version, changes: { status } },
      {
        onSuccess: () => {
          toast(
            status === "cancelled"
              ? t("appointments.cancelled")
              : t("appointments.marked", { status: t(STATUS_LABEL[status]) }),
          );
        },
        onError: (error) => {
          setRefusal(appointmentRefusal(error));
        },
      },
    );
  }

  return (
    <Drawer
      title={t("appointments.preview")}
      onClose={onClose}
      headerActions={
        appointment && canUpdate && open ? (
          <Button
            size="sm"
            onPress={() => {
              onEdit(appointment);
            }}
          >
            <Pencil size={13} aria-hidden="true" />
            {t("records.edit")}
          </Button>
        ) : null
      }
    >
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <LoadError error={query.error} onRetry={() => void query.refetch()} notFound={t("appointments.notFound")} />
      ) : (
        <>
          <div className="appointment-identity">
            <span className="appointment-strip" style={{ background: hostColour(query.data.host_user_id) }} />
            <div>
              <p className="drawer-name">{query.data.title}</p>
              <p className="drawer-headline">
                <TimeRange start={query.data.starts_at} end={query.data.ends_at} />
              </p>
            </div>
          </div>
          {refusal ? (
            <p className="notice error" role="alert">
              {t(refusal)}
            </p>
          ) : null}

          <section className="drawer-section" aria-labelledby="appointment-status-title">
            <h2 id="appointment-status-title" className="drawer-section-title">
              {t("appointments.field.status")}
            </h2>
            {open ? (
              <div className="status-choices" role="group" aria-labelledby="appointment-status-title">
                {STATUSES.map((status) => (
                  <AriaButton
                    key={status}
                    className={query.data.status === status ? `status-choice ${status} active` : "status-choice"}
                    aria-pressed={query.data.status === status}
                    isDisabled={!canUpdate || busy}
                    onPress={() => {
                      setStatus(status);
                    }}
                  >
                    {t(STATUS_LABEL[status])}
                  </AriaButton>
                ))}
              </div>
            ) : (
              <p>
                <Badge tone="neutral">{t("appointments.status.cancelled")}</Badge>{" "}
                <span className="muted">{t("appointments.cancelledHint")}</span>
              </p>
            )}
          </section>

          <dl className="field-list">
            <FieldRow label={t("appointments.field.host")}>{ownerLabel(t, query.data.host_user_id, meId)}</FieldRow>
            <FieldRow label={t("appointments.field.kind")}>
              {t(KIND_LABEL[query.data.kind])}
              {query.data.location ? <span className="appointment-note"> · {query.data.location}</span> : null}
            </FieldRow>
            <FieldRow label={t("appointments.field.contact")}>
              {query.data.contact ? (
                <AriaButton
                  className="record-link"
                  onPress={() => {
                    if (query.data.contact) onOpenContact(query.data.contact.id);
                  }}
                >
                  {query.data.contact.name}
                </AriaButton>
              ) : null}
            </FieldRow>
            <FieldRow label={t("appointments.field.note")}>
              {query.data.note ? <span className="appointment-note">{query.data.note}</span> : null}
            </FieldRow>
          </dl>

          {open && canUpdate ? (
            <div className="drawer-actions">
              <Button
                onPress={() => {
                  onEdit(query.data);
                }}
              >
                <CalendarClock size={14} aria-hidden="true" />
                {t("appointments.reschedule")}
              </Button>
              <Button
                variant="destructive"
                isDisabled={busy}
                onPress={() => {
                  setConfirming("cancel");
                }}
              >
                {t("appointments.cancel")}
              </Button>
            </div>
          ) : null}
          {canDelete ? (
            <div className="drawer-actions">
              <Button
                size="sm"
                isDisabled={busy}
                onPress={() => {
                  setConfirming("delete");
                }}
              >
                <Trash2 size={13} aria-hidden="true" />
                {t("appointments.delete")}
              </Button>
            </div>
          ) : null}
          <ConfirmDialog
            isOpen={confirming !== null}
            title={t(confirming === "delete" ? "appointments.deleteTitle" : "appointments.cancelTitle")}
            message={t(confirming === "delete" ? "appointments.deleteMessage" : "appointments.cancelMessage", {
              title: query.data.title,
            })}
            confirmLabel={t(confirming === "delete" ? "appointments.deleteConfirm" : "appointments.cancelConfirm")}
            onCancel={() => {
              setConfirming(null);
            }}
            onConfirm={() => {
              const what = confirming;
              setConfirming(null);
              if (what === "cancel") {
                setStatus("cancelled");
                return;
              }
              remove.mutate(
                { id: query.data.id },
                {
                  onSuccess: () => {
                    toast(t("appointments.deleted"));
                    onClose();
                  },
                  onError: (error) => {
                    setRefusal(appointmentRefusal(error));
                  },
                },
              );
            }}
          />
        </>
      )}
    </Drawer>
  );
}
