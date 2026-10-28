import { Copy, ExternalLink, Pencil, Plus, Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import { KINDS, type Kind } from "../api/appointments";
import {
  type BookingPage,
  type BookingPageChanges,
  bookingPath,
  HORIZON_MAX,
  LENGTHS,
  MAX_PAGES,
  NOTICES,
  STEPS,
  useBookingPages,
  useCreateBookingPage,
  useDeleteBookingPage,
  useUpdateBookingPage,
} from "../api/bookingPages";
import { newIdempotencyKey } from "../api/records";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { KIND_LABEL } from "./appointmentParts";
import { Drawer, type Option, ownerLabel } from "./parts";

/*
 * Calendar › Booking pages (decision P5-C 10): the workspace's pages, each
 * with its link, status and booking count. Owners and Admins create, edit,
 * publish, unpublish and delete them; everyone else reads. Publishing needs
 * the business hours (P5-C 3); the server says so and the message names
 * where to set them.
 */

type T = ReturnType<typeof useT>;

function refusal(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "business_hours_required") return "bookingPages.error.business_hours_required";
    if (error.code === "host_not_member") return "bookingPages.error.host_not_member";
    if (error.code === "stale_version") return "bookingPages.error.stale";
    if (error.status === 403) return "bookingPages.error.denied";
    if (error.status === 422) return "bookingPages.error.invalid";
  }
  return "bookingPages.error.generic";
}

function noticeLabel(t: T, minutes: number): string {
  if (minutes === 0) return t("bookingPages.notice.none");
  if (minutes % 1440 === 0) return t("bookingPages.notice.days", { count: minutes / 1440 });
  return t("bookingPages.notice.hours", { count: minutes / 60 });
}

export function BookingPagesDrawer({
  workspaceId,
  hosts,
  meId,
  canManage,
  onClose,
}: {
  workspaceId: string;
  hosts: Option[];
  meId: string | undefined;
  canManage: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const pages = useBookingPages(workspaceId);
  const update = useUpdateBookingPage(workspaceId);
  const remove = useDeleteBookingPage(workspaceId);
  const [editing, setEditing] = useState<BookingPage | "new" | null>(null);
  const [deleting, setDeleting] = useState<BookingPage | null>(null);
  const [failure, setFailure] = useState<MessageId | null>(null);
  const items = pages.data?.items ?? [];

  const setStatus = (page: BookingPage, status: BookingPage["status"]) => {
    setFailure(null);
    update.mutate(
      { id: page.id, version: page.version, changes: { status } },
      {
        onSuccess: () => {
          toast(t(status === "published" ? "bookingPages.publishedToast" : "bookingPages.unpublishedToast"));
        },
        onError: (error) => {
          setFailure(refusal(error));
        },
      },
    );
  };

  const copy = (page: BookingPage) => {
    const link = `${window.location.origin}${bookingPath(workspaceId, page.public_key)}`;
    void navigator.clipboard.writeText(link).then(
      () => {
        toast(t("bookingPages.copied"));
      },
      () => {
        toast(t("bookingPages.copyFailed"));
      },
    );
  };

  return (
    <Drawer
      title={t("bookingPages.title")}
      onClose={onClose}
      headerActions={
        canManage ? (
          <Button
            size="sm"
            variant="primary"
            isDisabled={items.length >= MAX_PAGES}
            onPress={() => {
              setEditing("new");
            }}
          >
            <Plus size={13} aria-hidden="true" />
            {t("bookingPages.new")}
          </Button>
        ) : null
      }
    >
      <p className="muted booking-intro">{t("bookingPages.intro")}</p>
      <p className="profile-note">{t("bookingPages.hoursNote")}</p>
      {failure ? (
        <p className="notice error" role="alert">
          {t(failure)}
        </p>
      ) : null}
      {pages.isPending ? (
        <Loading />
      ) : pages.isError ? (
        <LoadError error={pages.error} onRetry={() => void pages.refetch()} />
      ) : items.length === 0 ? (
        <p className="muted">{t(canManage ? "bookingPages.empty" : "bookingPages.emptyReadOnly")}</p>
      ) : (
        <ul className="booking-pages">
          {items.map((page) => {
            const path = bookingPath(workspaceId, page.public_key);
            const published = page.status === "published";
            return (
              <li key={page.id} className="booking-page-card">
                <div className="booking-page-head">
                  <span className="booking-page-name">{page.name}</span>
                  <Badge tone={published ? "success" : "neutral"}>
                    {t(published ? "bookingPages.published" : "bookingPages.draft")}
                  </Badge>
                </div>
                <p className="muted">
                  {t("bookingPages.summary", {
                    length: page.length_minutes,
                    kind: t(KIND_LABEL[page.kind]),
                    host: ownerLabel(t, page.host_user_id, meId),
                  })}
                  {" · "}
                  {t("bookingPages.count", { count: page.booking_count })}
                </p>
                {published ? (
                  <div className="booking-page-link">
                    <span className="sr-only">{t("bookingPages.link")}</span>
                    <a href={path} target="_blank" rel="noreferrer" className="booking-page-url">
                      <ExternalLink size={13} aria-hidden="true" />
                      {path}
                    </a>
                    <Button
                      size="sm"
                      onPress={() => {
                        copy(page);
                      }}
                    >
                      <Copy size={13} aria-hidden="true" />
                      {t("bookingPages.copy")}
                    </Button>
                  </div>
                ) : null}
                {canManage ? (
                  <div className="booking-page-actions">
                    <Button
                      size="sm"
                      variant={published ? "secondary" : "primary"}
                      isDisabled={update.isPending}
                      onPress={() => {
                        setStatus(page, published ? "draft" : "published");
                      }}
                    >
                      {t(published ? "bookingPages.unpublish" : "bookingPages.publish")}
                    </Button>
                    <Button
                      size="sm"
                      onPress={() => {
                        setEditing(page);
                      }}
                    >
                      <Pencil size={13} aria-hidden="true" />
                      {t("bookingPages.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onPress={() => {
                        setDeleting(page);
                      }}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                      {t("bookingPages.delete")}
                    </Button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {items.length >= MAX_PAGES && canManage ? (
        <p className="muted">{t("bookingPages.limit", { max: MAX_PAGES })}</p>
      ) : null}
      {editing ? (
        <BookingPageDialog
          workspaceId={workspaceId}
          page={editing === "new" ? undefined : editing}
          hosts={hosts}
          meId={meId}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
      <ConfirmDialog
        isOpen={deleting !== null}
        title={t("bookingPages.deleteTitle")}
        message={t("bookingPages.deleteBody")}
        confirmLabel={t("bookingPages.delete")}
        onCancel={() => {
          setDeleting(null);
        }}
        onConfirm={() => {
          if (!deleting) return;
          const id = deleting.id;
          setDeleting(null);
          remove.mutate(
            { id },
            {
              onSuccess: () => {
                toast(t("bookingPages.deleted"));
              },
              onError: (error) => {
                setFailure(refusal(error));
              },
            },
          );
        }}
      />
    </Drawer>
  );
}

function BookingPageDialog({
  workspaceId,
  page,
  hosts,
  meId,
  onClose,
}: {
  workspaceId: string;
  page: BookingPage | undefined;
  hosts: Option[];
  meId: string | undefined;
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateBookingPage(workspaceId);
  const update = useUpdateBookingPage(workspaceId);
  const [name, setName] = useState(page?.name ?? "");
  const [description, setDescription] = useState(page?.description ?? "");
  const [host, setHost] = useState(page?.host_user_id ?? meId ?? hosts[0]?.id ?? "");
  const [length, setLength] = useState<number>(page?.length_minutes ?? 30);
  const [step, setStep] = useState<number>(page?.step_minutes ?? 30);
  const [kind, setKind] = useState<Kind>(page?.kind ?? "video");
  const [location, setLocation] = useState(page?.location ?? "");
  const [notice, setNotice] = useState<number>(page?.notice_minutes ?? 240);
  const [horizon, setHorizon] = useState(String(page?.horizon_days ?? 30));
  const [failure, setFailure] = useState<MessageId | null>(null);
  const [key] = useState(newIdempotencyKey);
  const busy = create.isPending || update.isPending;
  const hostChoices = hosts.some((option) => option.id === host)
    ? hosts
    : [...hosts, { id: host, label: ownerLabel(t, host, meId) }];
  const notices: readonly number[] = NOTICES.some((value) => value === notice) ? NOTICES : [...NOTICES, notice];
  const horizonDays = Number(horizon);
  const horizonValid = Number.isInteger(horizonDays) && horizonDays >= 1 && horizonDays <= HORIZON_MAX;

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (!name.trim() || !horizonValid) {
      setFailure("bookingPages.error.invalid");
      return;
    }
    const values = {
      name: name.trim(),
      description: description.trim() || null,
      host_user_id: host,
      length_minutes: length,
      step_minutes: step,
      kind,
      location: location.trim() || null,
      notice_minutes: notice,
      horizon_days: horizonDays,
    };
    const failed = (error: unknown) => {
      setFailure(refusal(error));
    };
    if (!page) {
      create.mutate(
        { body: values, key },
        {
          onSuccess: () => {
            toast(t("bookingPages.created"));
            onClose();
          },
          onError: failed,
        },
      );
      return;
    }
    const changes: BookingPageChanges = {};
    for (const field of Object.keys(values) as (keyof typeof values)[]) {
      if (values[field] !== page[field]) Object.assign(changes, { [field]: values[field] });
    }
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    update.mutate(
      { id: page.id, version: page.version, changes },
      {
        onSuccess: () => {
          toast(t("bookingPages.saved"));
          onClose();
        },
        onError: failed,
      },
    );
  };

  return (
    <Dialog
      isOpen
      title={t(page ? "bookingPages.dialogEdit" : "bookingPages.dialogNew")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="booking-page-form" isDisabled={busy}>
            {t(page ? "bookingPages.save" : "bookingPages.create")}
          </Button>
        </>
      }
    >
      <form id="booking-page-form" className="record-form" onSubmit={submit} noValidate>
        <div className="form-field wide">
          <label htmlFor="booking-name" className="form-label">
            {t("bookingPages.field.name")}
          </label>
          <input
            id="booking-name"
            className="form-input"
            value={name}
            maxLength={120}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </div>
        <div className="form-field wide">
          <label htmlFor="booking-description" className="form-label">
            {t("bookingPages.field.description")}
          </label>
          <textarea
            id="booking-description"
            className="form-input form-textarea"
            rows={3}
            maxLength={1000}
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
            }}
          />
        </div>
        <div className="form-field">
          <label htmlFor="booking-host" className="form-label">
            {t("bookingPages.field.host")}
          </label>
          <select
            id="booking-host"
            className="form-input form-select"
            value={host}
            onChange={(event) => {
              setHost(event.target.value);
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
          <label htmlFor="booking-kind" className="form-label">
            {t("bookingPages.field.kind")}
          </label>
          <select
            id="booking-kind"
            className="form-input form-select"
            value={kind}
            onChange={(event) => {
              const next = KINDS.find((value) => value === event.target.value);
              if (next) setKind(next);
            }}
          >
            {KINDS.map((value) => (
              <option key={value} value={value}>
                {t(KIND_LABEL[value])}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="booking-length" className="form-label">
            {t("bookingPages.field.length")}
          </label>
          <select
            id="booking-length"
            className="form-input form-select"
            value={length}
            onChange={(event) => {
              setLength(Number(event.target.value));
            }}
          >
            {LENGTHS.map((minutes) => (
              <option key={minutes} value={minutes}>
                {t("bookingPages.minutes", { count: minutes })}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="booking-step" className="form-label">
            {t("bookingPages.field.step")}
          </label>
          <select
            id="booking-step"
            className="form-input form-select"
            value={step}
            onChange={(event) => {
              setStep(Number(event.target.value));
            }}
          >
            {STEPS.map((minutes) => (
              <option key={minutes} value={minutes}>
                {t("bookingPages.minutes", { count: minutes })}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="booking-notice" className="form-label">
            {t("bookingPages.field.notice")}
          </label>
          <select
            id="booking-notice"
            className="form-input form-select"
            value={notice}
            onChange={(event) => {
              setNotice(Number(event.target.value));
            }}
          >
            {notices.map((minutes) => (
              <option key={minutes} value={minutes}>
                {noticeLabel(t, minutes)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="booking-horizon" className="form-label">
            {t("bookingPages.field.horizon")}
          </label>
          <input
            id="booking-horizon"
            className="form-input"
            type="number"
            min={1}
            max={HORIZON_MAX}
            value={horizon}
            aria-invalid={!horizonValid}
            onChange={(event) => {
              setHorizon(event.target.value);
            }}
          />
        </div>
        <div className="form-field wide">
          <label htmlFor="booking-location" className="form-label">
            {t("bookingPages.field.location")}
          </label>
          <input
            id="booking-location"
            className="form-input"
            value={location}
            maxLength={300}
            aria-describedby="booking-location-hint"
            onChange={(event) => {
              setLocation(event.target.value);
            }}
          />
          <p id="booking-location-hint" className="form-hint">
            {t("bookingPages.field.locationHint")}
          </p>
        </div>
        {failure ? (
          <p className="notice error form-field wide" role="alert">
            {t(failure)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
