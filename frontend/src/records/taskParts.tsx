import { Calendar, Pencil, Plus, Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { useIntl } from "react-intl";
import { Button as AriaButton } from "react-aria-components";

import { ApiError } from "../api/client";
import { FieldErrors, newIdempotencyKey } from "../api/records";
import {
  dueFromPreset,
  type DuePreset,
  type Priority,
  PRIORITIES,
  type Task,
  type TaskCreate,
  useCreateTask,
  useDeleteTask,
  useUpdateTask,
} from "../api/tasks";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { type Option, OwnerCell } from "./parts";

/*
 * Pieces shared by the Tasks page and the record drawers' task sections
 * (decision P4-C): a task row (complete, links, priority, due, assignee,
 * edit, delete), the quick-add row of the design (title, assignee, due,
 * priority) and the edit dialog with an exact due date and time. Each
 * change sends the task's version; the server decides.
 */

export const PRIORITY_LABEL: Record<Priority, MessageId> = {
  high: "tasks.priority.high",
  medium: "tasks.priority.medium",
  low: "tasks.priority.low",
};

const REFUSALS: Record<string, MessageId> = {
  stale_version: "tasks.error.version",
  task_not_found: "tasks.error.gone",
  contact_not_found: "tasks.error.link",
  company_not_found: "tasks.error.link",
  opportunity_not_found: "tasks.error.link",
  assignee_not_member: "tasks.error.assignee",
};

export function taskRefusal(error: unknown): MessageId {
  if (error instanceof FieldErrors) return "tasks.error.title";
  if (error instanceof ApiError) {
    const known = error.code ? REFUSALS[error.code] : undefined;
    if (known) return known;
    if (error.status === 403) return "tasks.error.forbidden";
  }
  return "tasks.error.failed";
}

/** A due time in the viewer's locale: "Today, 5:00 PM" or "Fri, Oct 30, 5:00 PM". */
export function DueText({ value, overdue }: { value: string | null; overdue: boolean }) {
  const intl = useIntl();
  const t = useT();
  if (!value) return <span className="task-due muted">{t("tasks.noDue")}</span>;
  const due = new Date(value);
  const sameDay = due.toDateString() === new Date().toDateString();
  const time = intl.formatTime(due, { hour: "numeric", minute: "2-digit" });
  const label = sameDay
    ? t("tasks.dueToday", { time })
    : intl.formatDate(due, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  return (
    <time dateTime={value} className={overdue ? "task-due overdue" : "task-due"}>
      <Calendar size={12} aria-hidden="true" />
      {label}
    </time>
  );
}

export function TaskRow({
  workspaceId,
  task,
  meId,
  overdue,
  canUpdate,
  canDelete,
  onOpenLink,
  onEdit,
  onError,
}: {
  workspaceId: string;
  task: Task;
  meId: string | undefined;
  overdue: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onOpenLink?: ((kind: "contact" | "company" | "opportunity", id: string) => void) | undefined;
  onEdit: (task: Task) => void;
  onError: (message: MessageId) => void;
}) {
  const t = useT();
  const toast = useToast();
  const update = useUpdateTask(workspaceId);
  const remove = useDeleteTask(workspaceId);
  const [deleting, setDeleting] = useState(false);
  const links: ["contact" | "company" | "opportunity", { id: string; name: string }][] = [];
  if (task.contact) links.push(["contact", task.contact]);
  if (task.company) links.push(["company", task.company]);
  if (task.opportunity) links.push(["opportunity", task.opportunity]);
  return (
    <li className={task.done ? "task-row done" : "task-row"}>
      <input
        type="checkbox"
        className="task-check"
        checked={task.done}
        disabled={!canUpdate || update.isPending}
        aria-label={t(task.done ? "tasks.reopenTask" : "tasks.complete", { title: task.title })}
        onChange={() => {
          update.mutate(
            { id: task.id, version: task.version, changes: { done: !task.done } },
            {
              onSuccess: () => {
                toast(t(task.done ? "tasks.reopened" : "tasks.completed"));
              },
              onError: (error) => {
                onError(taskRefusal(error));
              },
            },
          );
        }}
      />
      <div className="task-main">
        <span className="task-title">{task.title}</span>
        {links.length ? (
          <span className="task-links">
            {links.map(([kind, link]) =>
              onOpenLink ? (
                <AriaButton
                  key={kind}
                  className="text-button task-link"
                  onPress={() => {
                    onOpenLink(kind, link.id);
                  }}
                >
                  {link.name}
                </AriaButton>
              ) : (
                <span key={kind} className="task-link">
                  {link.name}
                </span>
              ),
            )}
          </span>
        ) : null}
      </div>
      <span className={`priority-tag ${task.priority}`}>{t(PRIORITY_LABEL[task.priority])}</span>
      <DueText value={task.due_at} overdue={overdue && !task.done} />
      <span className="task-assignee">
        <OwnerCell ownerId={task.assignee_user_id} meId={meId} />
      </span>
      <span className="task-actions">
        {canUpdate ? (
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("tasks.edit", { title: task.title })}
            onPress={() => {
              onEdit(task);
            }}
          >
            <Pencil size={13} aria-hidden="true" />
          </Button>
        ) : null}
        {canDelete ? (
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("tasks.delete", { title: task.title })}
            isDisabled={remove.isPending}
            onPress={() => {
              setDeleting(true);
            }}
          >
            <Trash2 size={13} aria-hidden="true" />
          </Button>
        ) : null}
      </span>
      <ConfirmDialog
        isOpen={deleting}
        title={t("tasks.deleteTitle")}
        confirmLabel={t("tasks.deleteConfirm")}
        message={t("tasks.deleteMessage", { title: task.title })}
        onConfirm={() => {
          setDeleting(false);
          remove.mutate(
            { id: task.id },
            {
              onSuccess: () => {
                toast(t("tasks.deleted"));
              },
              onError: (error) => {
                onError(taskRefusal(error));
              },
            },
          );
        }}
        onCancel={() => {
          setDeleting(false);
        }}
      />
    </li>
  );
}

const PRESETS: [DuePreset, MessageId][] = [
  ["today", "tasks.due.today"],
  ["tomorrow", "tasks.due.tomorrow"],
  ["nextWeek", "tasks.due.nextWeek"],
  ["none", "tasks.due.none"],
];

/** The design's quick-add row: Enter or Add creates the task. */
export function QuickAdd({
  workspaceId,
  owners,
  meId,
  links,
  idPrefix,
  onError,
}: {
  workspaceId: string;
  owners: Option[];
  meId: string | undefined;
  /** Links every task added here gets (a record drawer's own record). */
  links?: Pick<TaskCreate, "contact_id" | "company_id" | "opportunity_id">;
  idPrefix: string;
  onError: (message: MessageId | null) => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateTask(workspaceId);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState(meId ?? "");
  const [due, setDue] = useState<DuePreset>("today");
  const [priority, setPriority] = useState<Priority>("medium");
  const [key, setKey] = useState(newIdempotencyKey);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const text = title.trim();
    if (!text) return;
    onError(null);
    create.mutate(
      {
        body: {
          title: text,
          priority,
          due_at: dueFromPreset(due),
          assignee_user_id: assignee || null,
          ...links,
        },
        key,
      },
      {
        onSuccess: () => {
          setTitle("");
          setKey(newIdempotencyKey());
          toast(t("tasks.added"));
        },
        onError: (error) => {
          onError(taskRefusal(error));
        },
      },
    );
  };

  return (
    <form className="task-add" onSubmit={submit}>
      <Plus size={15} aria-hidden="true" className="task-add-icon" />
      <label className="sr-only" htmlFor={`${idPrefix}-title`}>
        {t("tasks.newTitle")}
      </label>
      <input
        id={`${idPrefix}-title`}
        className="task-add-title"
        value={title}
        maxLength={200}
        placeholder={t("tasks.addPlaceholder")}
        onChange={(event) => {
          setTitle(event.target.value);
        }}
      />
      <label className="sr-only" htmlFor={`${idPrefix}-assignee`}>
        {t("tasks.field.assignee")}
      </label>
      <select
        id={`${idPrefix}-assignee`}
        className="form-input form-select task-add-select"
        value={assignee}
        onChange={(event) => {
          setAssignee(event.target.value);
        }}
      >
        <option value="">{t("records.owner.none")}</option>
        {owners.map((owner) => (
          <option key={owner.id} value={owner.id}>
            {owner.label}
          </option>
        ))}
      </select>
      <label className="sr-only" htmlFor={`${idPrefix}-due`}>
        {t("tasks.field.due")}
      </label>
      <select
        id={`${idPrefix}-due`}
        className="form-input form-select task-add-select"
        value={due}
        onChange={(event) => {
          setDue(event.target.value as DuePreset);
        }}
      >
        {PRESETS.map(([value, label]) => (
          <option key={value} value={value}>
            {t(label)}
          </option>
        ))}
      </select>
      <label className="sr-only" htmlFor={`${idPrefix}-priority`}>
        {t("tasks.field.priority")}
      </label>
      <select
        id={`${idPrefix}-priority`}
        className="form-input form-select task-add-select"
        value={priority}
        onChange={(event) => {
          setPriority(event.target.value as Priority);
        }}
      >
        {PRIORITIES.map((value) => (
          <option key={value} value={value}>
            {t(PRIORITY_LABEL[value])}
          </option>
        ))}
      </select>
      <Button type="submit" variant="primary" size="sm" isDisabled={!title.trim() || create.isPending}>
        {t("tasks.add")}
      </Button>
    </form>
  );
}

/** "2026-10-30T17:00" in the viewer's time zone, for a datetime-local field. */
function localInput(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function TaskDialog({
  workspaceId,
  task,
  owners,
  onClose,
}: {
  workspaceId: string;
  task: Task;
  owners: Option[];
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const update = useUpdateTask(workspaceId);
  const [title, setTitle] = useState(task.title);
  const [priority, setPriority] = useState<Priority>(task.priority);
  const [due, setDue] = useState(localInput(task.due_at));
  const [assignee, setAssignee] = useState(task.assignee_user_id ?? "");
  const [refusal, setRefusal] = useState<MessageId | null>(null);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const text = title.trim();
    if (!text) {
      setRefusal("tasks.error.title");
      return;
    }
    const dueAt = due ? new Date(due).toISOString() : null;
    const before = task.due_at ? new Date(task.due_at).toISOString() : null;
    const changes = {
      ...(text === task.title ? {} : { title: text }),
      ...(priority === task.priority ? {} : { priority }),
      ...(dueAt === before ? {} : { due_at: dueAt }),
      ...((assignee || null) === task.assignee_user_id ? {} : { assignee_user_id: assignee || null }),
    };
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    update.mutate(
      { id: task.id, version: task.version, changes },
      {
        onSuccess: () => {
          toast(t("records.saved"));
          onClose();
        },
        onError: (error) => {
          setRefusal(taskRefusal(error));
        },
      },
    );
  };

  return (
    <Dialog
      isOpen
      title={t("tasks.editTitle")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="task-form" isDisabled={update.isPending}>
            {t("records.saveChanges")}
          </Button>
        </>
      }
    >
      <form id="task-form" className="record-form" onSubmit={submit} noValidate>
        <div className="form-field wide">
          <label htmlFor="task-title" className="form-label">
            {t("tasks.field.title")}
          </label>
          <input
            id="task-title"
            className="form-input"
            value={title}
            maxLength={200}
            onChange={(event) => {
              setTitle(event.target.value);
            }}
          />
        </div>
        <div className="form-field">
          <label htmlFor="task-due" className="form-label">
            {t("tasks.field.due")}
          </label>
          <input
            id="task-due"
            className="form-input"
            type="datetime-local"
            value={due}
            onChange={(event) => {
              setDue(event.target.value);
            }}
          />
        </div>
        <div className="form-field">
          <label htmlFor="task-priority" className="form-label">
            {t("tasks.field.priority")}
          </label>
          <select
            id="task-priority"
            className="form-input form-select"
            value={priority}
            onChange={(event) => {
              setPriority(event.target.value as Priority);
            }}
          >
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {t(PRIORITY_LABEL[value])}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="task-assignee" className="form-label">
            {t("tasks.field.assignee")}
          </label>
          <select
            id="task-assignee"
            className="form-input form-select"
            value={assignee}
            onChange={(event) => {
              setAssignee(event.target.value);
            }}
          >
            <option value="">{t("records.owner.none")}</option>
            {owners.map((owner) => (
              <option key={owner.id} value={owner.id}>
                {owner.label}
              </option>
            ))}
          </select>
        </div>
        {refusal ? (
          <p className="notice error wide" role="alert">
            {t(refusal)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
